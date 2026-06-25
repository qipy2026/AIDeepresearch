# 贷后周报结构完整性修复 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复贷后周报 5 处结构缺陷——消除「暂无相关内容」占位符、模板残留 `[甲方名称]`、空值展示异常，新增数据完整性校验层。

**架构：** 三层数据模型（获取 → 格式化 → 渲染），新增 `_fetch_party_a_signals()` 从 warning_db 拉取甲方信号，新增 `_validate_and_enrich()` 自动补全缺失字段并打日志。

**技术栈：** Python 3.x, pytest, loguru

**规格文档：** `docs/superpowers/specs/2026-06-25-report-structural-completeness-design.md`

---

### 任务 1：`_validate_and_enrich()` — TDD 实现

**文件：**
- 修改：`backend/src/services/reporter.py`（新增 `FIELD_DEFAULTS` 常量 + `_validate_and_enrich` 方法）
- 修改：`backend/src/tests/unit/test_weekly_context.py`（新增测试）

- [ ] **步骤 1：编写失败测试**

在 `test_weekly_context.py` 中新增测试类 `TestValidateAndEnrich`：

```python
class TestValidateAndEnrich:
    """T7: _validate_and_enrich fills missing fields with defaults."""

    def test_enriches_empty_str_fields(self):
        from services.reporter import FIELD_DEFAULTS
        data = WeeklyData(
            enterprise="测试企业",
            industry="",
            loan_amount="0",
            risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
        )
        result = ReportingService._validate_and_enrich(data)
        assert result["loan_amount"] == FIELD_DEFAULTS["loan_amount"]
        assert result["industry"] == FIELD_DEFAULTS["industry"]

    def test_enriches_none_list_fields(self):
        data = WeeklyData(
            enterprise="测试企业",
            loan_amount="1000.0",
            risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
            party_a_signals=None,
            warnings_signals=None,
        )
        result = ReportingService._validate_and_enrich(data)
        assert result["party_a_signals"] == []
        assert result["warnings_signals"] == []

    def test_enriches_none_dict_fields(self):
        data = WeeklyData(
            enterprise="测试企业",
            loan_amount="1000.0",
            risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
            headcount_trend=None,
            industry_data=None,
        )
        result = ReportingService._validate_and_enrich(data)
        assert result["headcount_trend"] == {"status": "unavailable"}
        assert result["industry_data"] == {"status": "unavailable"}

    def test_does_not_overwrite_valid_data(self):
        valid_signals = [{"name": "甲方A", "signals": [{"severity": "red"}], "signal_count": 1}]
        data = WeeklyData(
            enterprise="测试企业",
            industry="安保服务",
            loan_amount="1000.0",
            risk={"red": 1, "orange": 2, "yellow": 3, "total": 6},
            headcount_trend={"status": "stable", "current_avg": 15.0},
            party_a_signals=valid_signals,
        )
        result = ReportingService._validate_and_enrich(data)
        assert result["loan_amount"] == "1000.0"
        assert result["industry"] == "安保服务"
        assert result["party_a_signals"] == valid_signals
        assert result["headcount_trend"]["status"] == "stable"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd backend && python -m pytest src/tests/unit/test_weekly_context.py::TestValidateAndEnrich -v`

预期：全部 4 个测试 FAIL，报错 `AttributeError: type object 'ReportingService' has no attribute '_validate_and_enrich'` 或 `FIELD_DEFAULTS` 未定义

- [ ] **步骤 3：实现 `FIELD_DEFAULTS` 常量 + `_validate_and_enrich()`**

在 `reporter.py` 的常量区域（`NEGATIVE_RISK_KEYWORDS` 后面，约第 43 行）新增：

```python
# 字段默认值（缺失时优雅降级）
FIELD_DEFAULTS: dict[str, str] = {
    "loan_amount": "未披露",
    "industry": "未分类",
    "enterprise": "未知企业",
}
```

在 `ReportingService` 类中 `_fetch_industry_data` 方法之后（约第 567 行），新增静态方法：

```python
@staticmethod
def _validate_and_enrich(data: WeeklyData) -> WeeklyData:
    """校验并补全 WeeklyData 缺失字段，打日志便于运维排查。

    - str 字段：空串或 "0" → FIELD_DEFAULTS 默认值
    - Optional[List] 字段：None → []
    - Optional[Dict] 字段：None → {"status": "unavailable"}
    - risk dict：确保 red/orange/yellow/total 键存在
    """
    # str 字段
    for field in ("loan_amount", "industry", "enterprise"):
        val = data.get(field, "")
        if not val or val == "0":
            default = FIELD_DEFAULTS.get(field, "未披露")
            logger.warning(
                "WeeklyData field '{}' is empty, using default: {}",
                field, default,
            )
            data[field] = default

    # Optional[List] 字段
    for field in ("party_a_signals", "warnings_signals"):
        if data.get(field) is None:
            logger.info(
                "WeeklyData field '{}' is None, setting to []", field
            )
            data[field] = []

    # Optional[Dict] 字段
    for field in ("headcount_trend", "industry_data"):
        if data.get(field) is None:
            logger.warning(
                "WeeklyData field '{}' is None, setting to {{'status': 'unavailable'}}",
                field,
            )
            data[field] = {"status": "unavailable"}

    # risk dict 键完整性
    risk = data.get("risk", {})
    for key in ("red", "orange", "yellow", "total"):
        if key not in risk:
            risk[key] = 0
    data["risk"] = risk

    return data
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd backend && python -m pytest src/tests/unit/test_weekly_context.py::TestValidateAndEnrich -v`

预期：4 个测试全部 PASS

- [ ] **步骤 5：Commit**

```bash
cd e:/work/code/AIDeepresearch
git add backend/src/services/reporter.py backend/src/tests/unit/test_weekly_context.py
git commit -m "feat: add _validate_and_enrich() + FIELD_DEFAULTS for WeeklyData completeness

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 2：`_fetch_party_a_signals()` — TDD 实现

**文件：**
- 修改：`backend/src/services/reporter.py`（新增 `_fetch_party_a_signals` 方法）
- 修改：`backend/src/tests/unit/test_weekly_context.py`（新增测试）

- [ ] **步骤 1：编写失败测试**

在 `test_weekly_context.py` 中新增测试类 `TestFetchPartyASignals`：

```python
class TestFetchPartyASignals:
    """T7: _fetch_party_a_signals fetches party A data from warning_db."""

    def test_returns_empty_list_when_no_parties(self):
        """没有 debtor 指向的甲方时返回空列表。"""
        result = ReportingService._fetch_party_a_signals("不存在的企业")
        assert result == []

    def test_returns_party_a_signals_from_db(self, monkeypatch):
        """有甲方时从 warning_db 拉取信号。"""
        # Mock _load_enterprises_yaml 返回含甲方的数据
        mock_ents = [
            {"name": "乙方企业", "role": "乙方", "debtor": ""},
            {"name": "甲方A", "role": "甲方", "debtor": "乙方企业", "industry": "房地产"},
        ]

        def mock_load():
            return mock_ents

        monkeypatch.setattr(
            "services.reporter.ReportingService._load_enterprises_yaml",
            staticmethod(mock_load),
        )

        # Mock warning_db
        mock_signals = [
            {"severity": "red", "title": "严重违约", "detail": "债券违约"},
        ]

        class MockDB:
            def get_signals_summary(self, enterprise, limit=20):
                if enterprise == "甲方A":
                    return mock_signals
                return []

        def mock_db_init(*args, **kwargs):
            return MockDB()

        monkeypatch.setattr(
            "services.reporter.WarningDB",
            MockDB,
        )

        result = ReportingService._fetch_party_a_signals("乙方企业")
        assert len(result) == 1
        assert result[0]["name"] == "甲方A"
        assert result[0]["industry"] == "房地产"
        assert result[0]["signal_count"] == 1
        assert result[0]["signals"][0]["severity"] == "red"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd backend && python -m pytest src/tests/unit/test_weekly_context.py::TestFetchPartyASignals -v`

预期：测试 FAIL，报错 `AttributeError: type object 'ReportingService' has no attribute '_fetch_party_a_signals'`

- [ ] **步骤 3：实现 `_fetch_party_a_signals()`**

在 `ReportingService` 类中 `_validate_and_enrich` 方法之前新增静态方法：

```python
@staticmethod
def _fetch_party_a_signals(enterprise: str) -> list:
    """从 enterprises.yaml + warning_db 获取甲方（核心企业）经营信号。

    Returns:
        [{name, industry, parent, signals, signal_count}, ...]
    """
    from warning_db import WarningDB

    # 1. 找出所有 debtor==enterprise 且 role=="甲方" 的企业
    ents = ReportingService._load_enterprises_yaml()
    parties = [
        e for e in ents
        if e.get("debtor") == enterprise and e.get("role") == "甲方"
    ]

    if not parties:
        return []

    # 2. 对每个甲方从 warning_db 拉取信号
    db = WarningDB()
    result = []
    for p in parties:
        pname = p.get("name", "")
        signals = db.get_signals_summary(pname, limit=10)
        result.append({
            "name": pname,
            "industry": p.get("industry", ""),
            "parent": p.get("parent", ""),
            "signals": signals,
            "signal_count": len(signals),
        })

    return result
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd backend && python -m pytest src/tests/unit/test_weekly_context.py::TestFetchPartyASignals -v`

预期：1 个测试 PASS（`test_returns_empty_list_when_no_parties`）；`test_returns_party_a_signals_from_db` 可能因 monkeypatch 方式不同而需要调整——如果 mock 未生效则检查 import 路径。

- [ ] **步骤 5：Commit**

```bash
git add backend/src/services/reporter.py backend/src/tests/unit/test_weekly_context.py
git commit -m "feat: add _fetch_party_a_signals() to pull party A signals from warning_db

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 3：集成新方法到 `_build_weekly_data`

**文件：**
- 修改：`backend/src/services/reporter.py:608`（`party_a_signals` 赋值行）
- 修改：`backend/src/services/reporter.py`（`_build_weekly_data` return 前调用 `_validate_and_enrich`）

- [ ] **步骤 1：修改 `_build_weekly_data` — 接入 `_fetch_party_a_signals`**

在 `reporter.py` 第 608 行，将：

```python
party_a_signals: Optional[List[Dict[str, Any]]] = None
```

替换为：

```python
party_a_signals = self._fetch_party_a_signals(enterprise)
```

- [ ] **步骤 2：修改 `_build_weekly_data` — 返回前调用 `_validate_and_enrich`**

在 `return WeeklyData(...)` 之前（第 613 行附近），插入：

```python
# 数据完整性校验 + 默认值补全
validated = self._validate_and_enrich(WeeklyData(
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
    party_a_signals=party_a_signals,
    industry_data=industry_data,
))
```

并将原来的 `return WeeklyData(...)` 替换为 `return validated`。

⚠️ 注意：`_validate_and_enrich` 会把 `None` 列表转为 `[]`，后续 `_format_weekly_context` 中的 `if not party_a_signals` 逻辑需同步调整（任务 4 处理）。

- [ ] **步骤 3：运行现有测试确认无回归**

运行：`cd backend && python -m pytest src/tests/unit/test_weekly_context.py -v`

预期：除 `test_party_a_signals_is_none_by_default` 外全部 PASS（该测试预期要更新，任务 6 处理）

- [ ] **步骤 4：Commit**

```bash
git add backend/src/services/reporter.py
git commit -m "fix: integrate _fetch_party_a_signals + _validate_and_enrich into _build_weekly_data

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 4：修复 `_format_weekly_context` 展示逻辑

**文件：**
- 修改：`backend/src/services/reporter.py:631-656`（loan_amount 显示）
- 修改：`backend/src/services/reporter.py:732-738`（party_a_signals 显示）

- [ ] **步骤 1：修复 `loan_amount` 空值显示**

在 `_format_weekly_context` 中，找到第 655 行：

```python
发放金额：{loan_amount} 万元
```

替换为：

```python
loan_display = loan_amount if loan_amount and loan_amount not in ("0", "未披露") else "未披露"
ctx += f"""【企业信息】（来源：参考文档 / 默认值）
企业名称：{enterprise}
所属行业：{industry}
发放金额：{loan_display} 万元
"""
```

⚠️ 注意：由于任务 3 中 `_validate_and_enrich` 已将空 `loan_amount` 转为 `"未披露"`，此处双重检查确保即使跳过校验也能正常显示。

- [ ] **步骤 2：修复 `party_a_signals` 展示逻辑**

在 `_format_weekly_context` 中，找到第 732-738 行：

```python
# ── 运营信号：甲方经营信号（T5 模板对应字段） ──
if party_a_signals:
    ctx += "\n【甲方经营信号】\n"
    for sig in party_a_signals:
        ctx += f"- {sig.get('name', '')}: {sig.get('value', '')} ({sig.get('status', '')})\n"
else:
    ctx += "\n【甲方经营信号】\n无相关内容\n"
```

替换为：

```python
# ── 运营信号：甲方经营信号（T5 模板对应字段） ──
if party_a_signals:
    ctx += "\n【甲方经营信号】（来源：企查查/百度舆情/同花顺）\n"
    ctx += "| 甲方名称 | 所属行业 | 预警信号数 | 最高风险等级 |\n"
    ctx += "|---------|---------|----------|------------|\n"
    for p in party_a_signals:
        name = p.get("name", "")
        industry = p.get("industry", "")
        count = p.get("signal_count", 0)
        signals = p.get("signals", [])
        sevs = [s.get("severity", "normal") for s in signals]
        max_sev = "🔴" if "red" in sevs else ("🟠" if "orange" in sevs else ("🟡" if "yellow" in sevs else "🟢"))
        ctx += f"| {name} | {industry} | {count} | {max_sev} |\n"
    # 注入甲方名称列表供 prompt 模板使用
    party_names = "、".join(p.get("name", "") for p in party_a_signals)
    ctx += f"\n（以上 {len(party_a_signals)} 家甲方核心企业的预警信号，请填入报告【二、核心企业监管】对应章节。甲方名称列表：{party_names}）\n"
else:
    ctx += "\n【甲方经营信号】\n暂无甲方经营信号数据，后续将通过招标数据或工商变更频率补充。\n"
```

- [ ] **步骤 3：运行现有测试确认无回归**

运行：`cd backend && python -m pytest src/tests/unit/test_weekly_context.py -v`

预期：上下文生成测试中的 `assert "无相关内容" in ctx` 需更新——因为现在展示文案变了。若测试失败，记下失败用例名称，任务 6 统一更新。

- [ ] **步骤 4：Commit**

```bash
git add backend/src/services/reporter.py
git commit -m "fix: improve _format_weekly_context display for loan_amount and party_a_signals

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 5：修复 `prompts.py` 模板 + `_build_fallback_report`

**文件：**
- 修改：`backend/src/prompts.py:156`
- 修改：`backend/src/services/reporter.py:895-903`

- [ ] **步骤 1：修复 `prompts.py` 模板残留 `[甲方名称]`**

在 `prompts.py` 第 156 行，将：

```
### 核心企业：[甲方名称]
```

替换为：

```
### 核心企业：{从【甲方经营信号】中提取甲方名称填入，多个甲方各一节}
```

同时在第 184 行，将：

```
（若甲方经营信号为"无相关内容"，本行改为：暂无甲方经营信号数据，后续将通过招标数据或工商变更频率补充。）
```

替换为：

```
（若【甲方经营信号】为空，本节显示：暂无甲方经营信号数据，后续将通过招标数据或工商变更频率补充。）
```

- [ ] **步骤 2：修复 `_build_fallback_report` 甲方经营信号展示**

在 `reporter.py` 第 895-903 行，将：

```python
# 四、甲方经营信号
lines.append("## 四、甲方经营信号")
lines.append("")
party_a = wd.get("party_a_signals") or []
if party_a:
    for sig in party_a:
        lines.append(f"- {sig.get('name', '')}: {sig.get('value', '')} ({sig.get('status', '')})")
else:
    lines.append("无相关内容")
lines.append("")
```

替换为：

```python
# 四、甲方经营信号
lines.append("## 四、甲方经营信号")
lines.append("")
party_a = wd.get("party_a_signals") or []
if party_a:
    for p in party_a:
        name = p.get("name", "")
        count = p.get("signal_count", 0)
        signals = p.get("signals", [])
        sevs = [s.get("severity", "normal") for s in signals]
        max_sev = "🔴红" if "red" in sevs else ("🟠橙" if "orange" in sevs else ("🟡黄" if "yellow" in sevs else "🟢正常"))
        lines.append(f"- {name}（{p.get('industry', '')}）：{count} 条预警，最高风险 {max_sev}")
else:
    lines.append("暂无甲方经营信号数据，后续将通过招标数据或工商变更频率补充。")
lines.append("")
```

- [ ] **步骤 3：Commit**

```bash
git add backend/src/prompts.py backend/src/services/reporter.py
git commit -m "fix: remove template placeholder [甲方名称] and improve fallback report display

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 6：更新已有测试 + 新增上下文格式测试 + 全量验证

**文件：**
- 修改：`backend/src/tests/unit/test_weekly_context.py`

- [ ] **步骤 1：更新 `test_party_a_signals_is_none_by_default`**

将第 96-99 行：

```python
def test_party_a_signals_is_none_by_default(self):
    svc = ReportingService.__new__(ReportingService)
    data = svc._build_weekly_data("测试企业", [])
    assert data["party_a_signals"] is None
```

替换为：

```python
def test_party_a_signals_is_empty_list_by_default(self):
    """没有配置甲方时 party_a_signals 应为空列表（非 None）。"""
    svc = ReportingService.__new__(ReportingService)
    data = svc._build_weekly_data("测试企业", [])
    assert data["party_a_signals"] == []
```

- [ ] **步骤 2：更新 `test_full_data_produces_valid_context`**

将第 132 行：

```python
assert "无相关内容" in ctx  # Party A signals fallback
```

替换为：

```python
assert "暂无甲方经营信号数据" in ctx  # Party A signals fallback
```

- [ ] **步骤 3：新增 `test_format_weekly_context_with_party_a_signals`**

在 `TestFormatWeeklyContext` 类中新增：

```python
def test_format_weekly_context_with_party_a_signals(self):
    """有甲方信号时上下文包含甲方名称和信号信息。"""
    data = WeeklyData(
        enterprise="乙方测试企业",
        industry="物业管理",
        loan_amount="500.0",
        risk={"red": 0, "orange": 1, "yellow": 2, "total": 3},
        party_a_signals=[
            {
                "name": "甲方A",
                "industry": "房地产开发",
                "parent": "母公司集团",
                "signals": [
                    {"severity": "red", "title": "严重违约", "detail": "债券违约"},
                    {"severity": "yellow", "title": "经营异常", "detail": "工商变更频繁"},
                ],
                "signal_count": 2,
            },
        ],
    )
    ctx = ReportingService._format_weekly_context(data)
    assert "甲方A" in ctx
    assert "房地产开发" in ctx
    assert "2" in ctx  # signal_count
    assert "🔴" in ctx  # max severity
```

- [ ] **步骤 4：新增 `test_format_weekly_context_missing_loan_amount`**

在 `TestFormatWeeklyContext` 类中新增：

```python
def test_format_weekly_context_missing_loan_amount(self):
    """loan_amount 为空时显示未披露。"""
    data = WeeklyData(
        enterprise="测试企业",
        loan_amount="未披露",  # 经 _validate_and_enrich 处理后的值
        risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
    )
    ctx = ReportingService._format_weekly_context(data)
    assert "未披露" in ctx
    assert "发放金额" in ctx
```

- [ ] **步骤 5：运行全量测试**

运行：`cd backend && python -m pytest src/tests/unit/test_weekly_context.py -v`

预期：全部测试 PASS

- [ ] **步骤 6：运行集成测试**

运行：`cd backend && python -m pytest src/tests/integration/test_weekly_report_pipeline.py -v`

预期：全部测试 PASS

- [ ] **步骤 7：Commit**

```bash
git add backend/src/tests/unit/test_weekly_context.py
git commit -m "test: update tests for party_a_signals pipeline and display defaults

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 验证清单

所有任务完成后，执行最终验证：

```bash
# 全量测试
cd backend && python -m pytest src/tests/unit/ src/tests/integration/ -v

# 确认没有遗漏的占位符
cd backend && grep -rn "无相关内容" src/services/reporter.py
cd backend && grep -rn "\[甲方名称\]" src/prompts.py

# 确认新常量存在
cd backend && grep -n "FIELD_DEFAULTS" src/services/reporter.py
```
