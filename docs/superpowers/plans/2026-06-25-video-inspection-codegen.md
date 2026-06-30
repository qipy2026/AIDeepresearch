# 视频巡检章节代码化生成 — 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将"四、现场视频巡检"章节从 LLM 模板中移除，改为纯代码从数据库拼装 Markdown，消除两阶段占位注入方案。

**架构：** `_build_video_inspection_section()` 新函数从聚合快照数据直接生成完整章节；LLM 模板用 `<!-- VIDEO_INSPECTION_PLACEHOLDER -->` 标记插入点；`generate_report()` 在 LLM 输出后替换占位标记为生成的章节。

**技术栈：** Python / FastAPI / SQLite / pytest

---

### 任务 1：新增 `camera_aggregated` 字段到 `WeeklyData`

**文件：**
- 修改：`backend/src/services/reporter.py:55-71`

- [ ] **步骤 1：在 WeeklyData TypedDict 中新增字段**

在 `key_snapshots` 行后添加一行：

```python
class WeeklyData(TypedDict, total=False):
    """贷后周报结构化上下文数据结构。字段缺失时格式化器使用优雅降级。"""

    enterprise: str
    industry: str
    loan_amount: str
    report_date: str
    report_period_start: str
    report_period_end: str
    ref_text: str
    risk: Dict[str, int]
    warnings_signals: Optional[List[Dict[str, Any]]]
    warnings_summary: Optional[Dict[str, Any]]
    headcount_trend: Optional[Dict[str, Any]]
    key_snapshots: Optional[List[Dict[str, Any]]]
    camera_aggregated: Optional[List[Dict[str, Any]]]  # 新增：完整小时级聚合快照数据
    party_a_signals: Optional[List[Dict[str, Any]]]
    industry_data: Optional[Dict[str, Any]]
```

- [ ] **步骤 2：验证 Python 语法无错误**

```bash
cd backend && python -c "from services.reporter import WeeklyData; print('OK')"
```

预期：`OK`

- [ ] **步骤 3：Commit**

```bash
git add backend/src/services/reporter.py
git commit -m "feat: add camera_aggregated field to WeeklyData TypedDict"
```

---

### 任务 2：修改 `_build_weekly_data()` 存储完整聚合数据

**文件：**
- 修改：`backend/src/services/reporter.py:754-785`

- [ ] **步骤 1：在 WeeklyData 构造中新增 `camera_aggregated`**

将第 769-784 行的 `WeeklyData(...)` 构造修改为：

```python
        # 构建 WeeklyData 并通过校验层补全缺失字段
        data = WeeklyData(
            enterprise=enterprise,
            industry=industry,
            loan_amount=loan_amount,
            report_date=today.strftime("%Y-%m-%d"),
            report_period_start=p_start,
            report_period_end=p_end,
            ref_text=ref_text,
            risk=risk,
            warnings_signals=db_warnings.get("signals", []),
            warnings_summary=db_warnings,
            headcount_trend=headcount_trend,
            key_snapshots=key_snaps if key_snaps else None,
            camera_aggregated=raw_snapshots,  # 新增：完整聚合数据，供 _build_video_inspection_section 使用
            party_a_signals=party_a_signals,
            industry_data=industry_data,
        )
```

- [ ] **步骤 2：验证语法**

```bash
cd backend && python -c "from services.reporter import ReportingService; print('OK')"
```

预期：`OK`

- [ ] **步骤 3：Commit**

```bash
git add backend/src/services/reporter.py
git commit -m "feat: store full camera aggregated data in WeeklyData"
```

---

### 任务 3：修改 `_format_weekly_context()` 删除关键时刻截图和占位指令

**文件：**
- 修改：`backend/src/services/reporter.py:864-888`

- [ ] **步骤 1：删除 `【关键时刻截图信息】` 区块和占位指令**

将第 864-888 行：

```python
        # ── 运营信号：视频巡检人数趋势（T4 模板对应字段） ──
        if headcount_trend and headcount_trend.get("status") != "insufficient":
            ctx += f"""
【视频巡检人数趋势】
趋势状态：{headcount_trend.get('status', 'unknown')}
本周日均人数：{headcount_trend.get('current_avg', 'N/A')}
前3周日均人数：{headcount_trend.get('prior_avg', 'N/A')}
变化幅度：{headcount_trend.get('delta_pct', 0) * 100:.1f}%
趋势说明：{headcount_trend.get('message', '')}
"""
            # 关键时刻截图（文本描述，不含 ![](url) —— 避免 DeepSeek 502）
            key_snaps = data.get("key_snapshots") or []
            if key_snaps:
                ctx += "\n【关键时刻截图信息】\n"
                for s in key_snaps:
                    ctx += (f"- {s['snapshot_date']} | 人数:{s['headcount']} | "
                            f"文件:{s['snapshot_path'].replace(chr(92),'/').split('/')[-1]}\n")
                ctx += "\n[重要] 报告[重点时段照片记录]节请写入以下占位文本（不要改动）：\n"
                ctx += "（占位，预备未来接入摄像头数据）\n"
        else:
            ctx += """
【视频巡检人数趋势】
趋势状态：insufficient
说明：数据不足，暂无法生成趋势
"""
```

替换为：

```python
        # ── 运营信号：视频巡检人数趋势 ──
        if headcount_trend and headcount_trend.get("status") != "insufficient":
            ctx += f"""
【视频巡检人数趋势】
趋势状态：{headcount_trend.get('status', 'unknown')}
本周日均人数：{headcount_trend.get('current_avg', 'N/A')}
前3周日均人数：{headcount_trend.get('prior_avg', 'N/A')}
变化幅度：{headcount_trend.get('delta_pct', 0) * 100:.1f}%
趋势说明：{headcount_trend.get('message', '')}
"""
        else:
            ctx += """
【视频巡检人数趋势】
趋势状态：insufficient
说明：数据不足，暂无法生成趋势
"""
```

- [ ] **步骤 2：运行现有测试确认趋势信息仍正常**

```bash
cd backend && python -m pytest src/tests/unit/test_video_trend.py::TestComputeHeadcountTrend -v
```

预期：PASS（趋势计算逻辑不变）

- [ ] **步骤 3：运行集成测试确认上下文格式变更**

```bash
cd backend && python -m pytest src/tests/integration/test_weekly_report_pipeline.py::TestWeeklyReportPipeline -v
```

预期：`test_key_snapshots_injected_into_context` 会失败（因为删除了截图文段），其余 PASS

- [ ] **步骤 4：Commit**

```bash
git add backend/src/services/reporter.py
git commit -m "refactor: remove key snapshot text and placeholder from LLM context"
```

---

### 任务 4：新增 `_build_video_inspection_section()` 静态方法

**文件：**
- 修改：`backend/src/services/reporter.py`（在 `_sync_snapshot_images` 之后，`_compute_headcount_trend` 之前插入）

- [ ] **步骤 1：编写失败的测试**

在 `backend/src/tests/unit/test_video_trend.py` 末尾追加新测试类：

```python
class TestBuildVideoInspectionSection:
    """T5: _build_video_inspection_section — code-generated video inspection chapter."""

    def test_full_data_generates_all_subsections(self):
        """有完整聚合数据和关键时刻截图 → 三个子节全部生成."""
        from services.reporter import ReportingService

        aggregated = [
            {"snapshot_date": "2026-06-20T14", "headcount": 7, "snapshot_path": "snap_20_14.jpg"},
            {"snapshot_date": "2026-06-24T09", "headcount": 4, "snapshot_path": "snap_24_09.jpg"},
            {"snapshot_date": "2026-06-24T14", "headcount": 8, "snapshot_path": "snap_24_14.jpg"},
        ]
        key_snaps = [
            {"snapshot_date": "2026-06-24T14", "headcount": 8,
             "snapshot_path": "snap_24_14.jpg"},
            {"snapshot_date": "2026-06-24T09", "headcount": 4,
             "snapshot_path": "snap_24_09.jpg"},
        ]
        headcount_trend = {
            "status": "stable",
            "current_avg": 6.0,
            "prior_avg": 6.5,
            "delta_pct": -0.077,
            "message": "→ 稳定，变化 7.7%",
        }

        result = ReportingService._build_video_inspection_section(
            aggregated, key_snaps, headcount_trend
        )

        assert "## 四、现场视频巡检" in result
        assert "### 重点时段统计" in result
        assert "### 历史对比" in result
        assert "### 重点时段照片记录" in result
        assert "snap_24_14.jpg" in result
        assert "snap_24_09.jpg" in result
        assert "8人" in result

    def test_empty_data_shows_fallback_text(self):
        """无聚合数据 → 各子节显示降级文本."""
        from services.reporter import ReportingService

        result = ReportingService._build_video_inspection_section([], [], None)

        assert "## 四、现场视频巡检" in result
        assert "暂无巡检数据" in result
        assert "暂无历史对比数据" in result
        assert "暂无快照数据" in result

    def test_partial_data_shows_dash_for_missing_hours(self):
        """某天只有14:00数据 → 09:00显示 '—'."""
        from services.reporter import ReportingService

        aggregated = [
            {"snapshot_date": "2026-06-24T14", "headcount": 5, "snapshot_path": ""},
        ]
        result = ReportingService._build_video_inspection_section(
            aggregated, [], None
        )

        assert "2026-06-24" in result
        assert "| — |" in result  # 09:00 missing
        assert "| 5 |" in result  # 14:00 present

    def test_no_trend_data_shows_fallback_in_history(self):
        """无趋势数据 → 历史对比显示降级文本."""
        from services.reporter import ReportingService

        aggregated = [
            {"snapshot_date": "2026-06-24T14", "headcount": 5, "snapshot_path": ""},
        ]
        result = ReportingService._build_video_inspection_section(
            aggregated, [], None
        )

        assert "暂无历史对比数据" in result
```

- [ ] **步骤 2：运行测试确认失败**

```bash
cd backend && python -m pytest src/tests/unit/test_video_trend.py::TestBuildVideoInspectionSection -v
```

预期：全部 4 个测试 FAIL，报 `AttributeError: type object 'ReportingService' has no attribute '_build_video_inspection_section'`

- [ ] **步骤 3：实现 `_build_video_inspection_section()`**

在 `reporter.py` 的 `_sync_snapshot_images` 方法之后（第 233 行之后）、`_read_camera_snapshots` 方法之前（第 236 行之前）插入：

```python
    @staticmethod
    def _build_video_inspection_section(
        aggregated: List[Dict[str, Any]],
        key_snapshots: List[Dict[str, Any]],
        headcount_trend: Optional[Dict[str, Any]],
    ) -> str:
        """纯代码生成"四、现场视频巡检"章节的 Markdown。

        不依赖 LLM——所有数据直接从已读取的摄像头数据库拼装。
        图片复制已在 _sync_snapshot_images 中完成，snapshot_path 此时为纯文件名。
        """
        lines = ["## 四、现场视频巡检", ""]
        lines.append("（注：一个企业通常配置4-6个摄像头点位，以下为巡检数据）")
        lines.append("")

        # ── 子节 1：重点时段统计 ──
        lines.append("### 重点时段统计")
        lines.append("")
        if not aggregated:
            lines.append("| 时段 | 时间戳 | 人数 | 场景 | 备注情况 |")
            lines.append("|------|--------|------|------|---------|")
            lines.append("| [暂无巡检数据] | | | | |")
            lines.append("")
        else:
            # 按日期分组，提取 09:00 和 14:00 人数
            from collections import defaultdict
            daily: Dict[str, Dict[str, int]] = defaultdict(dict)
            for s in aggregated:
                bucket = s.get("snapshot_date", "")  # "YYYY-MM-DDTHH"
                if "T" not in bucket:
                    continue
                date_str, hour_str = bucket.split("T", 1)
                hour = int(hour_str) if hour_str.isdigit() else None
                hc = s.get("headcount", 0)
                if hour is not None:
                    daily[date_str][hour] = hc

            lines.append("| 日期 | 09:00 人数 | 14:00 人数 | 日均人数 |")
            lines.append("|------|-----------|-----------|---------|")
            for day in sorted(daily.keys()):
                h9 = daily[day].get(9)
                h14 = daily[day].get(14)
                all_vals = list(daily[day].values())
                avg = round(sum(all_vals) / len(all_vals)) if all_vals else 0
                s9 = str(h9) if h9 is not None else "—"
                s14 = str(h14) if h14 is not None else "—"
                lines.append(f"| {day} | {s9} | {s14} | {avg} |")
            lines.append("")

        # ── 子节 2：历史对比 ──
        lines.append("### 历史对比")
        lines.append("")
        if headcount_trend and headcount_trend.get("status") not in ("insufficient", None):
            current_avg = headcount_trend.get("current_avg")
            prior_avg = headcount_trend.get("prior_avg")
            delta_pct = headcount_trend.get("delta_pct")
            message = headcount_trend.get("message", "")

            from datetime import date, timedelta
            today = date.today()
            # 本周范围
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)

            lines.append("| 周次 | 日期范围 | 日均人数 | 变化 |")
            lines.append("|------|---------|---------|------|")
            cur_str = f"{current_avg:.1f}" if current_avg is not None else "N/A"
            lines.append(
                f"| 本周 | {week_start.strftime('%m-%d')} ~ {week_end.strftime('%m-%d')} "
                f"| {cur_str} | — |"
            )
            if prior_avg is not None and delta_pct is not None:
                prior_start = week_start - timedelta(days=7)
                prior_end = week_start - timedelta(days=1)
                prior_str = f"{prior_avg:.1f}"
                direction = "+" if delta_pct > 0 else ""
                pct_str = f"{direction}{delta_pct * 100:.1f}%"
                lines.append(
                    f"| 前3周 | {prior_start.strftime('%m-%d')} ~ {prior_end.strftime('%m-%d')} "
                    f"| {prior_str} | {pct_str} |"
                )
            lines.append("")
            lines.append(f"趋势说明：{message}")
            lines.append("")
        else:
            lines.append("暂无历史对比数据")
            lines.append("")

        # ── 子节 3：重点时段照片记录 ──
        lines.append("### 重点时段照片记录")
        lines.append("")
        if key_snapshots:
            for s in key_snapshots:
                fname = s.get("snapshot_path", "").replace("\\", "/").split("/")[-1]
                if not fname:
                    continue
                lines.append(
                    f"![{s.get('snapshot_date', '')} {s.get('headcount', '?')}人]"
                    f"(/snapshots/{fname})"
                )
            lines.append("")
        else:
            lines.append("暂无快照数据")
            lines.append("")

        return "\n".join(lines) + "\n"
```

- [ ] **步骤 4：运行新测试确认通过**

```bash
cd backend && python -m pytest src/tests/unit/test_video_trend.py::TestBuildVideoInspectionSection -v
```

预期：全部 4 个测试 PASS

- [ ] **步骤 5：Commit**

```bash
git add backend/src/services/reporter.py backend/src/tests/unit/test_video_trend.py
git commit -m "feat: add _build_video_inspection_section() with tests"
```

---

### 任务 5：修改 `generate_report()` 删除占位注入 + 改用占位标记替换

**文件：**
- 修改：`backend/src/services/reporter.py:949-988`

- [ ] **步骤 1：修改 `generate_report()` 的截图处理逻辑**

将第 949-988 行：

```python
            # 截图后处理: LLM 只需生成占位文本，_inject_snapshot_images 负责替换为真实图片
            # 不在 prompt 中嵌入 ![](url) —— DeepSeek 等文本模型会因此 502
            _key_snaps = weekly_data.get("key_snapshots") or []
            if _key_snaps:
                prompt += (
                    "\n\n[重要] 报告[重点时段照片记录]节请写入以下占位文本（不要改动）：\n"
                    "（占位，预备未来接入摄像头数据）\n"
                )
        else:
            ...
        
        try:
            response = invoke_llm(self._config, system_prompt, prompt)
            report_text = response.strip()
        except Exception as _llm_err:
            ...
        
        # 后处理：注入关键时刻截图到报告 + 清理残留 localhost:5000 URL
        if self._style == "weekly":
            _key_snaps = weekly_data.get("key_snapshots") or []
            report_text = _inject_snapshot_images(report_text, _key_snaps)
```

替换为：

```python
        try:
            response = invoke_llm(self._config, system_prompt, prompt)
            report_text = response.strip()
        except Exception as _llm_err:
            logger.warning(
                "LLM 调用失败，降级为结构化报告: {}",
                _llm_err,
            )
            if self._style == "weekly":
                report_text = self._build_fallback_report(weekly_data, state)
            else:
                report_text = f"报告生成失败，LLM 服务不可用。\n\n错误: {_llm_err}"

        if self._config.strip_thinking_tokens:
            report_text = strip_thinking_tokens(report_text)
        report_text = strip_tool_calls(report_text).strip() or "报告生成失败，请检查输入。"

        # 后处理：用代码生成的视频巡检章节替换占位标记
        if self._style == "weekly":
            _aggregated = weekly_data.get("camera_aggregated") or []
            _key_snaps = weekly_data.get("key_snapshots") or []
            _trend = weekly_data.get("headcount_trend")
            video_section = ReportingService._build_video_inspection_section(
                _aggregated, _key_snaps, _trend
            )
            if "<!-- VIDEO_INSPECTION_PLACEHOLDER -->" in report_text:
                report_text = report_text.replace(
                    "<!-- VIDEO_INSPECTION_PLACEHOLDER -->", video_section
                )
            else:
                # 降级：LLM 未输出占位标记（极端情况），在报告末尾追加
                logger.warning("报告中未找到 VIDEO_INSPECTION_PLACEHOLDER，追加到末尾")
                report_text += "\n" + video_section
```

- [ ] **步骤 2：验证语法**

```bash
cd backend && python -c "from services.reporter import ReportingService; print('OK')"
```

预期：`OK`

- [ ] **步骤 3：Commit**

```bash
git add backend/src/services/reporter.py
git commit -m "refactor: replace snapshot placeholder injection with code-generated section"
```

---

### 任务 6：修改 `prompts.py` 删除视频巡检模板

**文件：**
- 修改：`backend/src/prompts.py:225-247`

- [ ] **步骤 1：将模板中"## 四、现场视频巡检"章节替换为占位标记**

将第 225-247 行（`## 四、现场视频巡检` 到 `（若【关键时刻截图】不存在则写"暂无快照数据"）`）替换为：

```python
---

<!-- VIDEO_INSPECTION_PLACEHOLDER -->

---
```

注意：保留前后的 `---` 分隔线。

- [ ] **步骤 2：验证 prompts 模块导入正常**

```bash
cd backend && python -c "from prompts import weekly_report_writer_instructions; print('OK')"
```

预期：`OK`

- [ ] **步骤 3：验证占位标记存在于 prompt 中**

```bash
cd backend && python -c "from prompts import weekly_report_writer_instructions; assert '<!-- VIDEO_INSPECTION_PLACEHOLDER -->' in weekly_report_writer_instructions; print('PLACEHOLDER_FOUND')"
```

预期：`PLACEHOLDER_FOUND`

- [ ] **步骤 4：Commit**

```bash
git add backend/src/prompts.py
git commit -m "refactor: replace video inspection template with code-gen placeholder"
```

---

### 任务 7：删除 `_inject_snapshot_images()` 函数

**文件：**
- 修改：`backend/src/services/reporter.py:74-112`

- [ ] **步骤 1：删除 `_inject_snapshot_images` 函数定义**

删除第 74-112 行的整个函数（含函数体、docstring、imports）。

- [ ] **步骤 2：更新使用该函数的测试**

**文件 `backend/src/tests/unit/test_video_trend.py`：**

删除整个 `TestInjectSnapshotImages` 类（第 406-458 行），以及文件顶部的 import：

```python
# 删除这行（如果存在）：
from services.reporter import _inject_snapshot_images
```

**文件 `backend/src/tests/integration/test_weekly_report_pipeline.py`：**

删除 `test_screenshot_injection_post_process` 测试方法（第 145-171 行），以及 `test_key_snapshots_injected_into_context` 测试方法（第 116-143 行，因为 `_format_weekly_context` 不再处理截图文本）。

同时删除文件顶部的 import（如果存在）：
```python
# 删除这行（如果存在）：
from services.reporter import _inject_snapshot_images
```

- [ ] **步骤 3：运行所有相关测试确认无引用错误**

```bash
cd backend && python -m pytest src/tests/unit/test_video_trend.py src/tests/integration/test_weekly_report_pipeline.py -v
```

预期：不再有引用 `_inject_snapshot_images` 的测试，全部剩余测试 PASS

- [ ] **步骤 4：Commit**

```bash
git add backend/src/services/reporter.py backend/src/tests/unit/test_video_trend.py backend/src/tests/integration/test_weekly_report_pipeline.py
git commit -m "refactor: remove _inject_snapshot_images() and related tests"
```

---

### 任务 8：更新 `_build_fallback_report()` 的视频巡检章节

**文件：**
- 修改：`backend/src/services/reporter.py:1048-1069`

- [ ] **步骤 1：将 fallback report 的视频巡检部分改用新函数**

将第 1048-1069 行：

```python
        # 三、视频巡检（从格式化上下文提取）
        lines.append("## 三、现场视频巡检")
        lines.append("")

        headcount = wd.get("headcount_trend", {}) or {}
        if headcount:
            lines.append(f"- 趋势状态：{headcount.get('status', 'unknown')}")
            lines.append(f"- 本周日均人数：{headcount.get('current_avg', 'N/A')}")
            lines.append(f"- 前3周日均人数：{headcount.get('prior_avg', 'N/A')}")
            if headcount.get('delta_pct') is not None:
                lines.append(f"- 变化幅度：{headcount['delta_pct'] * 100:.1f}%")
            lines.append(f"- 趋势说明：{headcount.get('message', '')}")
            lines.append("")

        lines.append("### 重点时段照片记录")
        lines.append("")
        key_snaps = wd.get("key_snapshots") or []
        if key_snaps:
            lines.append("（占位，预备未来接入摄像头数据）")
        else:
            lines.append("暂无快照数据")
        lines.append("")
```

替换为：

```python
        # 三、视频巡检（由代码从数据库数据生成）
        _aggregated = wd.get("camera_aggregated") or []
        _key_snaps = wd.get("key_snapshots") or []
        _trend = wd.get("headcount_trend")
        lines.append(
            ReportingService._build_video_inspection_section(
                _aggregated, _key_snaps, _trend
            )
        )
```

- [ ] **步骤 2：运行 fallback report 回归测试**

```bash
cd backend && python -m pytest src/tests/ -k "fallback" -v 2>/dev/null || echo "no_fallback_tests_found_manually_verify"
```

预期：无相关测试时手动验证，语法无错误

- [ ] **步骤 3：Commit**

```bash
git add backend/src/services/reporter.py
git commit -m "refactor: update fallback report to use _build_video_inspection_section"
```

---

### 任务 9：运行全量测试并手动端到端验证

**文件：** 无新文件，验证步骤

- [ ] **步骤 1：运行全部单元测试**

```bash
cd backend && python -m pytest src/tests/unit/ -v
```

预期：全部 PASS

- [ ] **步骤 2：运行全部集成测试**

```bash
cd backend && python -m pytest src/tests/integration/ -v
```

预期：全部 PASS（不可达的外部服务测试自动 skip）

- [ ] **步骤 3：启动后端服务并生成一份报告验证**

启动服务后触发一次研究，检查生成的报告：
- "四、现场视频巡检" 章节是否存在
- 是否包含 "重点时段统计"、"历史对比"、"重点时段照片记录" 三个子节
- 是否不再出现模板指令文本（"重要指令：在上方的【结构化数据】中查找..."）
- 是否不再出现 "占位" 文本
- 图片链接是否正确（`/snapshots/{filename}` 格式）

- [ ] **步骤 4：Commit（如有微调）**

```bash
git add -A
git commit -m "chore: final adjustments after E2E verification"
```

---

## 自检

### 1. 规格覆盖度

| 规格需求 | 对应任务 |
|---------|---------|
| 新增 `camera_aggregated` 字段 | 任务 1 |
| `_build_weekly_data` 存储完整聚合数据 | 任务 2 |
| `_format_weekly_context` 删除截图上下文 | 任务 3 |
| 新增 `_build_video_inspection_section()` | 任务 4 |
| `generate_report` 改用占位标记替换 | 任务 5 |
| `prompts.py` 删除模板、插入占位标记 | 任务 6 |
| 删除 `_inject_snapshot_images()` | 任务 7 |
| 更新 `_build_fallback_report()` | 任务 8 |
| 测试更新 | 任务 4、7 |
| `_sync_snapshot_images` 保留不变 | 无改动（确认保留） |
| 降级处理（占位标记缺失时追加到末尾） | 任务 5 |

### 2. 占位符扫描

无 "待定"/"TODO"/"后续实现"。所有代码步骤均有完整代码块。

### 3. 类型一致性

- `camera_aggregated: Optional[List[Dict[str, Any]]]` 在任务 1 定义，任务 2/5/8 使用 ✓
- `_build_video_inspection_section(aggregated, key_snapshots, headcount_trend)` 签名在任务 4 定义，任务 5/8 调用参数一致 ✓
- `<!-- VIDEO_INSPECTION_PLACEHOLDER -->` 在任务 6 插入模板，任务 5 替换，名称一致 ✓
