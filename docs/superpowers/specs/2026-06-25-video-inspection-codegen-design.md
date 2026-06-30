# 视频巡检章节代码化生成 — 设计规格

日期：2026-06-25 | 状态：待审查

## 背景

当前"四、现场视频巡检"章节由 LLM 根据结构化上下文生成，采用两阶段占位注入方案：
1. LLM 写入占位文本 `（占位，预备未来接入摄像头数据）`
2. `_inject_snapshot_images()` 后处理替换为真实图片

存在以下缺陷：
- 模板指令（"禁止使用占位"）与结构化数据指令（"写入占位文本"）互相矛盾
- 模板中的 "重要指令" 被 LLM 当成输出内容复制进报告
- "重点时段统计"和"历史对比"表格无法从数据库填充，显示"暂无数据"
- 两阶段方案本质脆弱，依赖 LLM 精确输出占位文本

## 目标

将"四、现场视频巡检"整章从 LLM 模板中移除，改为纯代码从数据库数据拼装 Markdown。
图片复制（`_sync_snapshot_images()`）逻辑保留不变。

## 数据流

```
counts.db → _read_camera_snapshots() → _attach_key_snapshots() → _sync_snapshot_images()
                                                                       ↓
                                                              图片已复制到本地
                                                               snapshot_path → 文件名
                                                                       ↓
                                          _build_video_inspection_section() → Markdown 章节
                                                                               ↓
                                                                   插入 LLM 报告（四章位置）
```

## 变更清单

### 1. `prompts.py` — 删除视频巡检模板

- 从 `<OUTPUT_FORMAT>` 中删除"## 四、现场视频巡检"整节（约 30 行，含 重点时段统计/历史对比/重点时段照片记录 及 "重要指令" 文本）
- 在"## 三"和"## 五"之间插入占位标记 `<!-- VIDEO_INSPECTION_PLACEHOLDER -->`，供代码替换
- `<REQUIREMENTS>` 中无需额外修改

### 2. `reporter.py` — 新增 `_build_video_inspection_section()`

新增静态方法，输入原始聚合快照数据、key_snapshots 列表和 headcount_trend dict，输出完整的 Markdown 章节。

#### 子节 2.1 重点时段统计

从聚合数据（`snapshot_date` 格式 `YYYY-MM-DDTHH`）按日期分组，提取每天 09:00 和 14:00 两个关键时段：

```markdown
### 重点时段统计

| 日期 | 09:00 人数 | 14:00 人数 | 日均人数 |
|------|-----------|-----------|---------|
| 2026-06-20 | — | 7 | 7 |
| 2026-06-24 | 4 | 8 | 6 |
```

- 某时段无数据时显示 "—"
- 日均 = 当天所有有效时段人数的平均值
- 如完全无数据，显示 "| [暂无巡检数据] | | | |"

#### 子节 2.2 历史对比

利用 `headcount_trend` 中的 `weeks_data` 字段：

```markdown
### 历史对比

| 周次 | 日期范围 | 日均人数 | 变化 |
|------|---------|---------|------|
| 本周 | 06-23 ~ 06-28 | 5.4 | — |
| 第-1周 | 06-16 ~ 06-22 | 7.1 | +31.5% |
| 第-2周 | 06-09 ~ 06-15 | 6.8 | +26.2% |
```

- 变化 = 该周相对于本周的百分比差值
- 数据不足时显示 "暂无历史对比数据"

#### 子节 2.3 重点时段照片记录

直接用 `key_snapshots` 生成图片链接：

```markdown
### 重点时段照片记录

![2026-06-20T14 7人](/snapshots/snap_office_13p_20260624_070654_497.jpg)
![2026-06-24T09 4人](/snapshots/snap_office_4p_20260624_070655_296.jpg)
![2026-06-24T14 8人](/snapshots/snap_office_6p_20260624_070516_941.jpg)
```

- 图片路径：`/snapshots/{snapshot_path 的文件名}`
- `key_snapshots` 为空时显示 "暂无快照数据"

### 3. `reporter.py` — 修改 `WeeklyData` 模型

新增字段 `camera_aggregated`，存储完整的小时级聚合数据：

```python
class WeeklyData(TypedDict, total=False):
    # ... 现有字段保持不变 ...
    camera_aggregated: Optional[List[Dict[str, Any]]]  # 新增
```

### 4. `reporter.py` — 修改 `_build_weekly_data()`

将 `_read_camera_snapshots()` 返回的完整聚合结果存入 `WeeklyData.camera_aggregated`：

```python
raw_snapshots = ReportingService._read_camera_snapshots(enterprise, weeks=4)
key_snaps = [s for s in raw_snapshots if s.get("snapshot_path")]

data = WeeklyData(
    # ... 现有字段 ...
    key_snapshots=key_snaps if key_snaps else None,
    camera_aggregated=raw_snapshots,  # 新增：完整聚合数据
)
```

### 5. `reporter.py` — 修改 `_format_weekly_context()`

- 删除 `【关键时刻截图信息】` 区块（约 8 行）
- 删除对应的 `[重要] 报告[重点时段照片记录]节请写入以下占位文本` 指令
- 保留 `【视频巡检人数趋势】` 区块（第三章"运营信号扫描"表格仍需此数据）

### 6. `reporter.py` — 修改 `generate_report()`

- 删除两处占位指令注入（line 952-957 和 prompt 末尾）
- LLM 生成后，调用 `_build_video_inspection_section()` 获取章节
- 替换模板中的 `<!-- VIDEO_INSPECTION_PLACEHOLDER -->` 为生成的章节
- 删除 `_inject_snapshot_images()` 调用
- 保留 `localhost:5000` URL 的兜底清理（该逻辑不依赖视频巡检）

```python
# 新流程
report_text = response.strip()
video_section = self._build_video_inspection_section(
    weekly_data.get("camera_aggregated", []),
    weekly_data.get("key_snapshots", []),
    weekly_data.get("headcount_trend"),
)
report_text = report_text.replace(
    "<!-- VIDEO_INSPECTION_PLACEHOLDER -->", video_section
)
```

### 7. `reporter.py` — 删除 `_inject_snapshot_images()`

函数完全删除（约 38 行）。

### 8. `reporter.py` — 修改 `_build_fallback_report()`

视频巡检章节改用 `_build_video_inspection_section()` 生成，移除硬编码的占位文本逻辑。

### 9. 测试更新

- 删除 `_inject_snapshot_images` 相关测试
- `_attach_key_snapshots` 和 `_sync_snapshot_images` 测试保留不变
- 新增 `_build_video_inspection_section` 测试：
  - 有完整数据 → 三个子节均正确生成
  - 无数据 → 各子节显示降级文本
  - 部分数据 → 缺失时段显示 "—"

## 不变项

- `_read_camera_snapshots()` — 不改
- `_attach_key_snapshots()` — 不改
- `_sync_snapshot_images()` — 不改（图片复制逻辑完整保留）
- `_compute_headcount_trend()` — 不改
- `CAMERA_DB_PATH` / `CAMERA_SNAPSHOT_SRC` / `CAMERA_SNAPSHOT_LOCAL` 配置 — 不改
- FastAPI `/snapshots/{filename}` 路由 — 不改

## 风险与降级

- 模板中 `<!-- VIDEO_INSPECTION_PLACEHOLDER -->` 是 HTML 注释，LLM 极不可能修改它
- 如果 LLM 输出中意外不包含占位标记（极端情况），在报告末尾追加视频巡检章节作为降级
- 图片复制失败时 `snapshot_path` 被清空，`_build_video_inspection_section()` 检测到空路径后不生成对应图片链接

## 影响范围

| 文件 | 变更类型 | 估算行数 |
|------|---------|---------|
| `prompts.py` | 删除 + 新增占位标记 | -30 +1 |
| `reporter.py` | 新增函数 + 修改多处 + 删除函数 | +80 -50 |
| 测试文件 | 新增 + 删除 | +40 -20 |

合计约 2 个源文件，净增约 50 行。
