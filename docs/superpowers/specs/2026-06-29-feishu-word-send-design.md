# 发送 Word 报告到飞书群 — 设计规格

日期: 2026-06-29
状态: 待实现
范围: ReportEditPage → send-to-feishu API → lark-cli

## 目标

将报告编辑页的"发送飞书"功能从发送截断 Markdown 文本改为发送完整 Word (.docx) 文件，确保中文字体和排版质量。

## 决策记录

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 覆盖 vs 新增 | 替换现有 Markdown 发送 | 用户明确要求 Word 版本 |
| 发送方式 | 直接发送文件到群 (`--file`) | lark-cli 原生支持，步骤最少，群内预览体验好 |
| 转换引擎 | 复用 `convert_to_docx.py` | 已有中文排版适配（宋体/黑体/楷体） |

## 数据流

```
用户点击"发送飞书(Word)"
  → 弹出模态框：选择/搜索群聊 (不变)
  → POST /api/reports/{id}/send-to-feishu { chat_id }
      → 读取 backend/reports/{id}.md
      → convert_to_docx.py: convert_md_to_docx_bytes() → BytesIO
      → 写入临时 .docx 文件
      → lark-cli im +messages-send --chat-id {chat_id} --file {tmp.docx} --as bot
      → 清理临时文件
  → 返回 { status: "ok", chat_id }
```

## 改动清单

### 后端 — `convert_to_docx.py`

新增函数：

```python
def convert_md_to_docx_bytes(md_path: str) -> BytesIO:
    """将 Markdown 转为 Word，返回内存 BytesIO。
    复用现有样式: 宋体正文/黑体标题/楷体引用/1.5倍行距/首行缩进。
    """
```

实现方式：提取现有 `convert_md_to_docx` 的核心逻辑，改为接收内存 buffer 而非文件路径。

### 后端 — `main.py`

重写 `POST /api/reports/{report_id}/send-to-feishu`：

- **删除**：4000 字节截断逻辑
- **新增**：MD→Word 转换 + 临时文件 + lark-cli `--file` 发送
- **错误码**：
  - 404: 报告不存在
  - 400: chat_id 为空
  - 500: Word 生成失败
  - 502: 飞书发送失败/超时

### 前端 — `ReportEditPage.vue`

| 位置 | 改动 |
|------|------|
| 第 39 行 | 按钮文案 `📨 发送飞书` → `📨 发送飞书(Word)` |
| 第 328 行 | 成功 toast → `"Word 报告已发送到群"` |
| 第 331 行 | 失败 toast → 保持不变 |

其余逻辑（模态框、群列表加载、选中、保存）完全不变。

## 字体与排版

已由 `convert_to_docx.py` 覆盖：

| 元素 | 字体 | 字号 | 其他 |
|------|------|------|------|
| 正文 | 宋体 | 12pt | 1.5 倍行距，首行缩进 0.74cm |
| H1 | 黑体 | 16pt | 加粗 |
| H2 | 黑体 | 14pt | 加粗 |
| H3 | 黑体 | 12pt | 加粗 |
| 表格 | 宋体/黑体 | 10.5pt | 深蓝表头，交替行背景 |
| 引用 | 楷体 | 10.5pt | 斜体，左缩进 |
| 代码 | Consolas | 9pt | 无行距 |
| 页边距 | — | — | 上/下 2.54cm，左/右 3.17cm |

## 测试计划

### 单元测试

1. `convert_to_docx_bytes` 正常 Markdown → 可被 python-docx 打开的 BytesIO
2. 空 content / 纯标题 / 含表格 / 含代码块 均不崩溃
3. 临时文件在发送成功/失败后均已清理

### 集成测试

4. `PUT /api/reports/{id}` 保存编辑内容
5. `POST /api/reports/{id}/send-to-feishu` chat_id 为空 → 400
6. 有效 chat_id → 200 (需 mock lark-cli)

### 手工验证

7. 在报告编辑页编辑"成都瑜環物业服务有限公司"报告
8. 点击"发送飞书(Word)" → 选择群 → 发送
9. 在飞书群内验证：收到 .docx 文件，中文字体正确，排版无乱码

## 约束

- lark-cli 必须已安装且已通过 `--as bot` 认证
- 服务器需安装宋体、黑体、楷体字体（否则 Word 会使用替代字体）
- 不改变现有的群列表获取逻辑 (`/api/feishu/chats`)
- 不改变前端模态框 UI
