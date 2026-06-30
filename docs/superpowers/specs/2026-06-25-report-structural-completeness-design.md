# 贷后周报结构完整性修复 — 设计文档

日期：2026-06-25　|　状态：已确认　|　方案：C（混合策略）

## 一、问题陈述

贷后监管综合周报中存在大量「暂无相关内容」占位符和模板残留，根因不在 LLM 而是在代码层——数据链路断裂、空值展示不当、prompt 模板残留。

### 根因清单

| # | 文件:行号 | 缺陷 | 报告表现 |
|---|----------|------|---------|
| ① | `reporter.py:608` | `party_a_signals = None` 硬编码，整条数据链路无人写入 | 二、甲方经营信号 → 永远「无相关内容」 |
| ② | `reporter.py:597-598` | `loan_amount` 从 YAML/RAG 查不到时为空字符串 | 头部 `发放金额： 万元`（数字缺失） |
| ③ | `prompts.py:156` | 模板残留 `### 核心企业：[甲方名称]` | LLM 照抄 `[甲方名称]` 到最终报告 |
| ④ | `reporter.py:738` | `party_a_signals` 为空时上下文输出「无相关内容」 | LLM 无从发挥，忠实照搬 |
| ⑤ | `reporter.py:895-903` | `_build_fallback_report` 同样写死「无相关内容」 | LLM 降级模式下同样空洞 |

## 二、方案选择：方案 C（混合策略）

1. **紧急修复**（5 处代码缺陷），1 小时内完成
2. **数据完整性校验层**：新增 `_validate_and_enrich()` 方法，自动检测缺失字段、填充合理默认值、打 warning 日志

## 三、架构设计

当前架构是两层模型（获取 → 格式化），缺失字段时直接输出空串或「无相关内容」。改造为三层模型：

```
获取层 (Data Sources)          格式化层 (Format)           渲染层 (Display)
─────────────────────         ────────────────            ───────────────

warning_log
  ├─ get_signals_summary()  ─┐                            输出到 prompt context
  ├─ get_warnings_*()         │                           │
  └─ ...                      │    _format_weekly_context()│   LLM 报告
                              ├──► 每个字段独立格式化 ────►
enterprises.yaml              │                           │
  ├─ loan_amount              │    _validate_and_enrich()  │   fallback 报告
  ├─ industry                 │    (新增)校验 + 默认值注入 │
  └─ party_a info             │
                              │
RAG (ChromaDB)               ─┘
  └─ rag_query()
```

## 四、详细设计

### 4.1 新增方法：`_fetch_party_a_signals(enterprise, tasks) -> List[Dict]`

从两个来源拉取甲方信号：

1. `enterprises.yaml`：找出所有 `debtor==enterprise` 且 `role=="甲方"` 的企业
2. `warning_db.get_signals_summary()`：查每个甲方的预警信号（企查查 + 百度舆情 + 同花顺）

返回结构：
```python
[
  {
    "name": "新街里南城都汇",
    "industry": "房地产开发",
    "parent": "",
    "signals": [...],        # 来自 warning_db
    "signal_count": 3,
  },
  ...
]
```

### 4.2 新增方法：`_validate_and_enrich(data: WeeklyData) -> WeeklyData`

在 `_build_weekly_data` 最后一步调用。按字段类型规则校验：

- **str 字段**（`loan_amount`, `industry`）：空串或 `"0"` → 替换为 `FIELD_DEFAULTS` 中的默认值，打 `log.warning`
- **Optional[List] 字段**（`party_a_signals`, `warnings_signals`）：`None` → 替换为 `[]`，打 `log.info`
- **Optional[Dict] 字段**（`headcount_trend`, `industry_data`）：`None` → 替换为 `{"status": "unavailable"}`，打 `log.warning`
- **risk dict**：确保 `red/orange/yellow/total` 键存在，缺失 → `0`

### 4.3 新增常量：`FIELD_DEFAULTS`

```python
FIELD_DEFAULTS: dict[str, str] = {
    "loan_amount": "未披露",
    "industry": "未分类",
    "enterprise": "未知企业",
}
```

### 4.4 修复 ①：`party_a_signals` 数据管线

文件：`reporter.py:608`

```python
# 之前
party_a_signals: Optional[List[Dict[str, Any]]] = None

# 之后
party_a_signals = self._fetch_party_a_signals(enterprise, tasks)
```

### 4.5 修复 ②：`loan_amount` 空值显示

文件：`reporter.py` `_format_weekly_context` 方法

```python
# 之前
f"发放金额：{loan_amount} 万元"

# 之后
loan_display = loan_amount if loan_amount and loan_amount != "0" else "未披露"
f"发放金额：{loan_display} 万元"
```

### 4.6 修复 ③：模板残留 `[甲方名称]`

文件：`prompts.py:156` + `reporter.py:_format_weekly_context`

两处联动：
1. Prompt 模板中 `[甲方名称]` → `{甲方名称}`，增加指令要求 LLM 从结构化数据提取
2. `_format_weekly_context` 中 `【甲方经营信号】` 节前插入甲方名称列表

### 4.7 修复 ④⑤：数据驱动展示

文件：`reporter.py:737-738` + `reporter.py:898-903`

`_format_weekly_context` 和 `_build_fallback_report` 两处统一改为数据驱动。当 `party_a_signals` 为空时：

```
暂无甲方经营信号数据，后续将通过招标数据或工商变更频率补充。
```

## 五、修复前后效果对比

以「成都瑜璟物业服务有限公司」报告为例：

| 报告区域 | 修复前 | 修复后 |
|---------|--------|--------|
| 报告头部 | `发放金额： 万元` | `发放金额：未披露` |
| 核心企业 | `### 核心企业：[甲方名称]` | `### 核心企业：新街里南城都汇` |
| 甲方经营信号 | `无相关内容` | `新街里南城都汇：3条预警 \| 四川能投润嘉：1条预警` |
| 债务企业核查 | `暂无相关内容` | 有数据时填真实内容，无数据时填 `暂无相关信息` |
| party_a_signals | 永远 `None` | 从 warning_db 动态拉取 |

## 六、测试策略

### 更新现有测试

- `test_party_a_signals_is_none_by_default`：断言从 `is None` 改为 `== []`

### 新增测试用例（`test_weekly_context.py`）

| 测试 | 内容 |
|------|------|
| `test_party_a_signals_fetched_from_db` | Mock warning_db 返回甲方数据，断言 party_a_signals 非空且结构正确 |
| `test_party_a_signals_empty_when_no_parties` | enterprises.yaml 中无甲方，断言 party_a_signals = [] |
| `test_validate_enriches_empty_fields` | loan_amount="" → "未披露"，party_a_signals=None → [] |
| `test_validate_does_not_overwrite_valid_data` | 有效数据不被默认值覆盖 |
| `test_format_weekly_context_with_party_a_signals` | party_a_signals 有数据时上下文包含甲方名称 |

## 七、影响范围

| 文件 | 改动量 | 类型 |
|------|--------|------|
| `reporter.py` | ~100 行新增 + ~15 行修改 | 新增 2 个方法 + 修改 5 处 |
| `prompts.py` | ~3 行修改 | 模板占位符替换 |
| `test_weekly_context.py` | ~50 行新增 + 1 行修改 | 新增 5 个测试 + 更新 1 个 |
| **总计** | **~170 行** | **集中在 3 个文件** |

## 八、实现步骤

```
Step 1: 新增 _fetch_party_a_signals()              — reporter.py
Step 2: 新增 _validate_and_enrich() + FIELD_DEFAULTS — reporter.py
Step 3: 修改 _build_weekly_data 调用新方法           — reporter.py
Step 4: 修改 _format_weekly_context 展示逻辑         — reporter.py
Step 5: 修改 _build_fallback_report 展示逻辑         — reporter.py
Step 6: 修改 prompts.py 模板占位符                   — prompts.py
Step 7: 更新/新增测试                                — test_weekly_context.py
Step 8: 运行全量测试验证                             — pytest
```
