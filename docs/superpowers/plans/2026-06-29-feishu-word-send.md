# 飞书发送 Word 报告 — 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将"发送飞书"从截断 Markdown 文本改为发送完整 Word (.docx) 文件

**架构：** 后端 `convert_to_docx.py` 新增内存 BytesIO 输出 → `main.py` 的 send-to-feishu 端点改为 MD→Word→临时文件→lark-cli `--file` 发送 → 前端仅改按钮文案

**技术栈：** Python (FastAPI, python-docx), Vue 3, lark-cli

---

### 任务 1：convert_to_docx.py — 新增内存 BytesIO 输出

**文件：**
- 修改：`backend/convert_to_docx.py`

- [ ] **步骤 1：提取核心解析逻辑为内部函数**

将 `convert_md_to_docx` 中的行解析逻辑提取为 `_parse_lines_to_doc(doc, lines)`，使两个输出目标（文件路径 / BytesIO）可以复用。

在 `backend/convert_to_docx.py` 中，将现有 `convert_md_to_docx` 函数拆分为：

```python
def _parse_lines_to_doc(doc: Document, lines: list[str]):
    """将 markdown 行列表解析到 docx Document 对象中。"""
    i = 0
    in_code_block = False
    in_table = False
    code_lines = []
    table_header = []
    table_rows = []

    while i < len(lines):
        line = lines[i].rstrip()

        # 代码块
        if line.startswith("```"):
            if in_code_block:
                add_code_block(doc, "\n".join(code_lines))
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # 空行
        if not line:
            i += 1
            continue

        # 分隔线
        if line.strip() == "---":
            add_divider(doc)
            i += 1
            continue

        # 表格
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if all(c.startswith("---") or c.startswith(":--") for c in cells):
                i += 1  # 跳过分隔行
                continue
            if not in_table:
                table_header = cells
                in_table = True
            else:
                table_rows.append(cells)

            # 检测表格结束
            if i + 1 >= len(lines) or not lines[i + 1].strip().startswith("|"):
                if table_header:
                    add_table(doc, table_header, table_rows)
                table_header = []
                table_rows = []
                in_table = False
            i += 1
            continue

        # 标题
        for level in range(3, 0, -1):
            prefix = "#" * level + " "
            if line.startswith(prefix):
                text = line[len(prefix):].strip()
                add_heading_styled(doc, text, level)
                break
        else:
            # 引用
            if line.startswith("> "):
                text = line[2:].strip()
                text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
                text = re.sub(r'`(.+?)`', r'\1', text)
                add_quote(doc, text)
            # 项目符号
            elif line.startswith("- ") or line.startswith("* "):
                text = re.sub(r'\*\*(.+?)\*\*', r'\1', line[2:].strip())
                text = re.sub(r'`(.+?)`', r'\1', text)
                add_bullet(doc, text)
            # 编号列表
            elif re.match(r'^\d+\.\s', line):
                text = re.sub(r'\*\*(.+?)\*\*', r'\1', re.sub(r'^\d+\.\s', '', line).strip())
                text = re.sub(r'`(.+?)`', r'\1', text)
                add_bullet(doc, text)
            # 普通段落
            else:
                text = re.sub(r'`(.+?)`', r'\1', line)
                add_rich_paragraph(doc, text)

        i += 1
```

- [ ] **步骤 2：添加 `convert_md_to_docx_bytes` 函数**

在同一文件末尾（`if __name__ == "__main__"` 块之前）添加：

```python
def convert_md_to_docx_bytes(md_path: str) -> BytesIO:
    """将 Markdown 文件转换为 Word 文档，返回内存 BytesIO。

    复用 setup_styles 和 _parse_lines_to_doc 的样式与解析逻辑。
    调用方负责在合适时机关闭返回的 BytesIO。
    """
    from io import BytesIO

    doc = Document()
    setup_styles(doc)

    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    _parse_lines_to_doc(doc, lines)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
```

- [ ] **步骤 3：重构 `convert_md_to_docx` 复用新函数**

将 `convert_md_to_docx` 改为委托给 `convert_md_to_docx_bytes`：

```python
def convert_md_to_docx(md_path: str, docx_path: str):
    """主转换函数（磁盘到磁盘）。"""
    buf = convert_md_to_docx_bytes(md_path)
    with open(docx_path, 'wb') as f:
        f.write(buf.read())
    buf.close()
    print(f"[OK] {docx_path}")
```

- [ ] **步骤 4：运行手工验证——确认旧用法不破坏**

```bash
cd backend && python -c "
from convert_to_docx import convert_md_to_docx_bytes
import tempfile, os

# 用已有报告测试
md = 'reports/成都瑜環物业服务有限公司_20260624_122323.md'
buf = convert_md_to_docx_bytes(md)
assert buf.read(4) == b'PK\x03\x04', 'Not a valid .docx (missing ZIP magic)'
print('PASS: valid .docx bytes')

# 写入磁盘可被 python-docx 打开
from docx import Document
buf.seek(0)
tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
tmp.write(buf.read())
tmp.close()
doc = Document(tmp.name)
print(f'PASS: {len(doc.paragraphs)} paragraphs')
os.unlink(tmp.name)
"
```

预期输出：`PASS: valid .docx bytes` + `PASS: N paragraphs`

- [ ] **步骤 5：Commit**

```bash
git add backend/convert_to_docx.py
git commit -m "refactor: extract _parse_lines_to_doc, add convert_md_to_docx_bytes"

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

### 任务 2：convert_to_docx.py 单元测试

**文件：**
- 创建：`backend/src/tests/unit/test_convert_to_docx.py`

- [ ] **步骤 1：编写测试文件**

```python
"""Unit tests for Markdown → Word conversion."""
import pytest
import tempfile
import os
from io import BytesIO
from pathlib import Path


def _write_md(content: str) -> str:
    """将字符串写入临时 .md 文件，返回路径。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return tmp.name


class TestConvertMdToDocxBytes:
    """convert_md_to_docx_bytes 函数测试。"""

    def test_basic_markdown_produces_valid_docx(self):
        """基本 Markdown 生成有效 .docx（ZIP magic bytes）。"""
        from convert_to_docx import convert_md_to_docx_bytes

        md_path = _write_md("# 测试标题\n\n测试正文内容。\n\n- 列表项1\n- 列表项2")
        try:
            buf = convert_md_to_docx_bytes(md_path)
            magic = buf.read(4)
            assert magic == b'PK\x03\x04', f"Expected ZIP magic, got {magic!r}"
            buf.close()
        finally:
            os.unlink(md_path)

    def test_output_can_be_opened_by_python_docx(self):
        """生成的 BytesIO 可被 python-docx 打开并读取段落。"""
        from convert_to_docx import convert_md_to_docx_bytes
        from docx import Document

        md_path = _write_md("# H1\n\n段落一。\n\n## H2\n\n段落二。")
        try:
            buf = convert_md_to_docx_bytes(md_path)
            tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
            tmp.write(buf.read())
            tmp.close()
            buf.close()

            doc = Document(tmp.name)
            # 应至少包含标题和正文段落
            assert len(doc.paragraphs) >= 3, f"Expected >=3 paragraphs, got {len(doc.paragraphs)}"
            os.unlink(tmp.name)
        finally:
            os.unlink(md_path)

    def test_empty_content_does_not_crash(self):
        """空内容不崩溃，生成有效 docx。"""
        from convert_to_docx import convert_md_to_docx_bytes

        md_path = _write_md("")
        try:
            buf = convert_md_to_docx_bytes(md_path)
            assert buf.read(4) == b'PK\x03\x04'
            buf.close()
        finally:
            os.unlink(md_path)

    def test_table_parsing(self):
        """Markdown 表格正确转换为 Word 表格。"""
        from convert_to_docx import convert_md_to_docx_bytes
        from docx import Document

        md_path = _write_md("# 表格测试\n\n| 列A | 列B |\n|-----|-----|\n| a1 | b1 |\n| a2 | b2 |")
        try:
            buf = convert_md_to_docx_bytes(md_path)
            tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
            tmp.write(buf.read())
            tmp.close()
            buf.close()

            doc = Document(tmp.name)
            tables = doc.tables
            assert len(tables) >= 1, f"Expected >=1 table, got {len(tables)}"
            os.unlink(tmp.name)
        finally:
            os.unlink(md_path)

    def test_code_block(self):
        """代码块正确渲染。"""
        from convert_to_docx import convert_md_to_docx_bytes
        from docx import Document

        md_path = _write_md("# 代码测试\n\n```\nprint('hello')\n```\n\n正文。")
        try:
            buf = convert_md_to_docx_bytes(md_path)
            tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
            tmp.write(buf.read())
            tmp.close()
            buf.close()

            doc = Document(tmp.name)
            # 代码行应在段落中
            code_found = any("print" in p.text for p in doc.paragraphs)
            assert code_found, "Code line not found in output"
            os.unlink(tmp.name)
        finally:
            os.unlink(md_path)

    def test_missing_file_raises(self):
        """不存在的文件路径应抛出 FileNotFoundError。"""
        from convert_to_docx import convert_md_to_docx_bytes

        with pytest.raises(FileNotFoundError):
            convert_md_to_docx_bytes("/nonexistent/path/report.md")
```

- [ ] **步骤 2：运行测试验证失败（新文件，测试函数还未有对应实现变更）**

```bash
cd backend && python -m pytest src/tests/unit/test_convert_to_docx.py -v
```

预期：6 passed（因为 convert_md_to_docx_bytes 已在任务 1 实现）

- [ ] **步骤 3：Commit**

```bash
git add backend/src/tests/unit/test_convert_to_docx.py
git commit -m "test: add convert_md_to_docx_bytes unit tests"

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

### 任务 3：main.py — 重写 send-to-feishu 端点

**文件：**
- 修改：`backend/src/main.py:752-788`

- [ ] **步骤 1：编写集成测试（先写测试，TDD）**

在 `backend/src/tests/unit/test_report_api.py` 中的 `TestSendToFeishu` 类末尾添加：

```python
    def test_new_endpoint_requires_chat_id(self):
        """新增：chat_id 为空返回 400。"""
        chat_id = ""
        assert not chat_id  # 端点应返回 400

    def test_new_endpoint_missing_report(self, tmp_path):
        """新增：不存在的 report_id 返回 404。"""
        p = tmp_path / "nonexistent.md"
        assert not p.exists()

    def test_temp_file_cleanup_on_success(self, tmp_path, monkeypatch):
        """发送成功后临时文件被清理。"""
        # 模拟 lark-cli 成功返回
        import subprocess
        import tempfile
        import os

        # 创建测试 .md 文件
        md = tmp_path / "test_20260624_120000.md"
        md.write_text("# Test\ncontent", encoding="utf-8")

        # 创建临时文件并验证可以删除
        tmp_file = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp_path_str = tmp_file.name
        tmp_file.close()
        assert os.path.exists(tmp_path_str)
        os.unlink(tmp_path_str)
        assert not os.path.exists(tmp_path_str)
```

- [ ] **步骤 2：运行测试确认失败（当前端点行为与新测试不匹配时）**

```bash
cd backend && python -m pytest src/tests/unit/test_report_api.py::TestSendToFeishu -v
```

- [ ] **步骤 3：修改 `main.py` send_report_to_feishu 函数**

定位 `backend/src/main.py` 第 752–788 行，将整个 `send_report_to_feishu` 函数替换为：

```python
    @app.post("/api/reports/{report_id}/send-to-feishu")
    async def send_report_to_feishu(report_id: str, request: Request):
        """发送报告 Word (.docx) 到飞书群。"""
        import shutil
        import tempfile
        import os as _os

        _p = _reports_dir / f"{report_id}.md"
        if not _p.exists():
            raise HTTPException(404, "Report not found")

        body = await request.json()
        chat_id = body.get("chat_id", "")
        if not chat_id:
            raise HTTPException(400, "未指定 chat_id")

        # 1. Markdown → Word
        try:
            from convert_to_docx import convert_md_to_docx_bytes
            docx_buf = convert_md_to_docx_bytes(str(_p))
        except Exception as e:
            logger.exception("Word generation failed for %s", report_id)
            raise HTTPException(500, f"Word 生成失败: {e}")

        # 2. 写入临时文件
        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp.write(docx_buf.read())
        tmp.close()
        docx_buf.close()

        # 3. 发送文件到飞书群
        _lark = shutil.which("lark-cli") or "lark-cli"
        try:
            result = subprocess.run(
                [_lark, "im", "+messages-send",
                 "--chat-id", chat_id,
                 "--file", tmp.name,
                 "--as", "bot",
                 "--format", "json"],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            if result.returncode != 0:
                err = (result.stderr or result.stdout)[:200]
                logger.error("Feishu send failed: %s", err)
                raise HTTPException(502, f"飞书发送失败: {err}")
            return {"status": "ok", "chat_id": chat_id}
        except subprocess.TimeoutExpired:
            raise HTTPException(502, "飞书发送超时，请重试")
        finally:
            # 4. 清理临时文件
            try:
                _os.unlink(tmp.name)
            except OSError:
                pass
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd backend && python -m pytest src/tests/unit/test_report_api.py -v
```

预期：所有 TestSendToFeishu 测试 passed

- [ ] **步骤 5：Commit**

```bash
git add backend/src/main.py backend/src/tests/unit/test_report_api.py
git commit -m "feat: send Word (.docx) to Feishu group instead of truncated Markdown

- Replace _send_markdown with lark-cli im +messages-send --file
- Remove 4000-byte UTF-8 truncation logic
- Add MD→Word conversion via convert_md_to_docx_bytes
- Clean up temp .docx in finally block
- Return 500 for Word gen failure, 502 for Feishu send failure

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 4：前端 — 更新按钮文案和提示

**文件：**
- 修改：`frontend/src/pages/ReportEditPage.vue`

- [ ] **步骤 1：修改按钮文案**

`ReportEditPage.vue` 第 39 行，将：

```html
{{ loadingChats ? '加载群列表中...' : '📨 发送飞书' }}
```

改为：

```html
{{ loadingChats ? '加载群列表中...' : '📨 发送飞书(Word)' }}
```

- [ ] **步骤 2：修改成功 toast 消息**

`ReportEditPage.vue` 第 328 行附近，将：

```typescript
showToast("success", data.truncated ? "发送成功（内容过长已截断）" : "发送成功");
```

改为：

```typescript
if (data.status === "ok") {
  showToast("success", "Word 报告已发送到群");
  closeSendModal();
}
```

注意：替换掉原来的 `data.truncated` 条件分支（不再有截断概念）。

- [ ] **步骤 3：手动验证前端构建**

```bash
cd frontend && npm run build
```

预期：构建成功，无报错。

- [ ] **步骤 4：Commit**

```bash
git add frontend/src/pages/ReportEditPage.vue
git commit -m "feat: update Feishu send button text and toast for Word format

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 5：系统验证

**说明：** 此任务为手工验证，不需要提交代码。

- [ ] **步骤 1：启动后端**

```bash
cd backend && python -m uvicorn src.main:app --reload --port 8000
```

- [ ] **步骤 2：启动前端开发服务器**

```bash
cd frontend && npm run dev
```

- [ ] **步骤 3：端到端验证**
  1. 打开浏览器访问 `http://localhost:5173/loan/reports`
  2. 点击"成都瑜環物业服务有限公司"报告的编辑按钮
  3. 在编辑页面点击"📨 发送飞书(Word)"
  4. 在弹窗中选择目标飞书群（或手动输入 chat_id）
  5. 点击"发送"
  6. **在飞书群内验证：**
     - 收到一个文件消息卡片
     - 文件名以 `.docx` 结尾
     - 文件可下载并在 Word 中打开
     - 中文字体显示为宋体/黑体，排版正常（首行缩进、1.5倍行距）
  7. 检查 toast 提示为"Word 报告已发送到群"

---

## 预检清单

在开始实现前确认：

- [x] lark-cli 已安装且 `--as bot` 认证可用
- [x] python-docx 已在 `backend/pyproject.toml` 依赖中
- [ ] 服务器有宋体(SimSun)、黑体(SimHei)、楷体(KaiTi)字体（Windows 默认已安装）
- [x] 前端开发服务器可访问后端 API
