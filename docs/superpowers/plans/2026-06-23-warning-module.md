# 实时预警模块 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 构建贷后监管实时预警模块——6数据源并行采集 → L1关键词预筛 → L2 LLM分级 → 飞书推送 → 前端仪表盘

**架构：** APScheduler in-process 调度 → Collector 微服务并行采集（每个独立容错）→ L1 yaml关键词匹配 → L2 LLM分级 → Dispatcher 飞书推送 → SQLite WAL 存储

**技术栈：** Python/FastAPI/APScheduler/Playwright, Vue3/Vite, SQLite WAL, 同花顺 iFinD SDK

---

## P0: 安全修复

### 任务 1: 轮换 qichacha_mcp.py 硬编码 token

**文件：**
- 修改: `backend/src/services/qichacha_mcp.py:11-36`
- 修改: `backend/.env`

- [ ] **步骤 1: 将 token 移到 .env**

`backend/.env` 新增：
```env
QICHACHA_MCP_TOKEN=MNU3SlOkHxnjAR1sw6ZgbAFMPXhKWNA6FPp4XYvVKbhXP0rV
```

`backend/src/services/qichacha_mcp.py` 修改 `MCP_CONFIG`：
```python
import os

_QCC_TOKEN = os.getenv("QICHACHA_MCP_TOKEN", "")

MCP_CONFIG: dict[str, dict[str, str]] = {
    "company": {
        "url": "https://agent.qcc.com/mcp/company/stream",
        "token": _QCC_TOKEN,
    },
    "risk": {
        "url": "https://agent.qcc.com/mcp/risk/stream",
        "token": _QCC_TOKEN,
    },
    "operation": {
        "url": "https://agent.qcc.com/mcp/operation/stream",
        "token": _QCC_TOKEN,
    },
    "executive": {
        "url": "https://agent.qcc.com/mcp/executive/stream",
        "token": _QCC_TOKEN,
    },
    "ipr": {
        "url": "https://agent.qcc.com/mcp/ipr/stream",
        "token": _QCC_TOKEN,
    },
    "history": {
        "url": "https://agent.qcc.com/mcp/history/stream",
        "token": _QCC_TOKEN,
    },
}
```

- [ ] **步骤 2: 验证**

```bash
cd backend && python -c "from src.services.qichacha_mcp import call_tool; r = call_tool('company', 'get_company_profile', {'keyword': '四川振海'}); print('OK' if r else 'FAIL')"
```

预期：认证正常，返回数据或空（网络问题不算失败）

- [ ] **步骤 3: Commit**

```bash
git add backend/src/services/qichacha_mcp.py backend/.env
git commit -m "fix: move qichacha MCP token from hardcoded to env var
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## P1: 基础设施

### 任务 2: 扩展 Configuration 类

**文件：**
- 修改: `backend/src/config.py`
- 修改: `backend/.env`

- [ ] **步骤 1: 添加 WarningConfig**

`backend/src/config.py` 新增：
```python
class WarningConfig(BaseModel):
    """实时预警模块配置。"""
    cron_interval: int = Field(default=300, description="采集间隔（秒）")
    source_timeout: int = Field(default=30, description="单源超时（秒）")
    keywords_path: str = Field(default="./config/keywords.yaml")
    red_max_delay: int = Field(default=300, description="红色最大延迟（秒）")
    daily_push_time: str = Field(default="18:00", description="日汇总推送时间")
    enabled_sources: str = Field(default="all", description="启用的数据源，逗号分隔")
    llm_timeout: int = Field(default=15, description="预警专用LLM超时（秒）")
    qichacha_token: str = Field(default="", description="企查查MCP Token")
    dm_username: str = Field(default="", description="DM查债通用户名")
    dm_password: str = Field(default="", description="DM查债通密码")
    ths_username: str = Field(default="", description="同花顺用户名")
    ths_password: str = Field(default="", description="同花顺密码")
    feishu_bot_token: str = Field(default="", description="飞书Bot Token")

    @classmethod
    def from_env(cls) -> "WarningConfig":
        return cls(
            cron_interval=int(os.getenv("WARNING_CRON_INTERVAL", "300")),
            source_timeout=int(os.getenv("WARNING_SOURCE_TIMEOUT", "30")),
            keywords_path=os.getenv("WARNING_KEYWORDS_PATH", "./config/keywords.yaml"),
            red_max_delay=int(os.getenv("WARNING_RED_MAX_DELAY", "300")),
            daily_push_time=os.getenv("WARNING_DAILY_PUSH_TIME", "18:00"),
            enabled_sources=os.getenv("WARNING_ENABLED_SOURCES", "all"),
            llm_timeout=int(os.getenv("WARNING_LLM_TIMEOUT", "15")),
            qichacha_token=os.getenv("QICHACHA_MCP_TOKEN", ""),
            dm_username=os.getenv("DM_USERNAME", ""),
            dm_password=os.getenv("DM_PASSWORD", ""),
            ths_username=os.getenv("THS_USERNAME", ""),
            ths_password=os.getenv("THS_PASSWORD", ""),
            feishu_bot_token=os.getenv("FEISHU_BOT_TOKEN", ""),
        )
```

- [ ] **步骤 2: 验证**

```bash
cd backend && python -c "from src.config import WarningConfig; c = WarningConfig.from_env(); print(f'cron={c.cron_interval}, timeout={c.source_timeout}')"
```

预期：cron=300, timeout=30

- [ ] **步骤 3: Commit**

---

### 任务 3: 创建 keywords.yaml 关键词库

**文件：**
- 创建: `backend/config/keywords.yaml`
- 修改: `backend/src/services/reporter.py:24-27`

- [ ] **步骤 1: 编写 keywords.yaml**

```yaml
# 预警关键词库 — L1预筛用
fatal:
  - 死亡
  - 爆炸
  - 火灾
  - 查封
  - 失联
  - 跑路
  - 重大事故
  - 立案调查

severe:
  - 违约
  - 诉讼
  - 冻结
  - 调查
  - 停产
  - 裁员
  - 暂停上市
  - 评级下调
  - 债务逾期
  - 司法拍卖

watch:
  - 下降
  - 亏损
  - 延期
  - 处罚
  - 警告
  - 减持
  - 辞职
  - 变更
  - 质疑
  - 投诉
```

- [ ] **步骤 2: 修改 reporter.py 导入同一文件**

`backend/src/services/reporter.py` 修改：
```python
import yaml
from pathlib import Path

_KEYWORDS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "keywords.yaml"

def _load_report_keywords() -> List[str]:
    """从 keywords.yaml 加载报告用风险关键词（三组合并）。"""
    with open(_KEYWORDS_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("fatal", []) + data.get("severe", []) + data.get("watch", [])

NEGATIVE_RISK_KEYWORDS: List[str] = _load_report_keywords()
```

- [ ] **步骤 3: 验证**

```bash
cd backend && python -c "from src.services.reporter import NEGATIVE_RISK_KEYWORDS; print(len(NEGATIVE_RISK_KEYWORDS)); print(NEGATIVE_RISK_KEYWORDS[:5])"
```

预期：所有三组合并后的关键词列表

- [ ] **步骤 4: Commit**

---

### 任务 4: 创建 enterprises.yaml 企业注册表

**文件：**
- 创建: `backend/config/enterprises.yaml`

```yaml
# 监管企业注册表
enterprises:
  - name: 四川振海保安服务有限公司
    stock_code: ""           # 未上市
    bond_code: ""            # 待确认
    industry: 安保服务
    loan_amount: 1000.0
    parent_enterprises: []   # 核心企业（甲方）
    keywords: [四川振海, 振海保安]

  - name: 国家管网集团西南管道有限责任公司重庆输油气分公司
    stock_code: ""           # 未上市（母公司国家管网未上市）
    concept_code: "885692.TI"  # 地下管网概念
    industry: 管道运输
    parent_enterprises:
      - 国家管网集团
    keywords: [国家管网, 西南管道]

  - name: 中铁建物业管理有限公司成都分公司
    stock_code: "601186.SH"  # 母公司中国铁建上市
    industry: 物业管理
    parent_enterprises:
      - 中国铁建
    keywords: [中铁建物业, 中国铁建]
```

- [ ] **步骤 1: 验证**

```bash
cd backend && python -c "
import yaml
with open('config/enterprises.yaml') as f:
    data = yaml.safe_load(f)
print(f'企业数: {len(data[\"enterprises\"])}')
for e in data['enterprises']:
    print(f'  {e[\"name\"][:20]}... stock={e[\"stock_code\"] or \"无\"}')
"
```

- [ ] **步骤 2: Commit**

---

### 任务 5: 创建 warning_db.py 数据库模型

**文件：**
- 创建: `backend/src/warning_db.py`
- 创建: `backend/src/tests/unit/test_warning_db.py`

- [ ] **步骤 1: 编写失败的测试**

```python
# backend/src/tests/unit/test_warning_db.py
import pytest
import sqlite3
from pathlib import Path

def test_warning_log_insert():
    from warning_db import WarningDB
    db = WarningDB(":memory:")
    db.init()
    wid = db.insert(
        enterprise="测试企业",
        source="test",
        severity="red",
        category="舆情",
        title="测试预警",
        detail="详细描述",
        suggested_action="建议措施",
        raw_data='{"key": "value"}'
    )
    assert wid > 0

def test_warning_log_dedup():
    from warning_db import WarningDB
    db = WarningDB(":memory:")
    db.init()
    # 两次插入同一预警应合并
    wid1 = db.insert("测试企业", "test", "red", "舆情", "同一标题", "", "", "")
    wid2 = db.insert("测试企业", "test", "red", "舆情", "同一标题", "", "", "")
    assert wid1 == wid2  # 去重返回同一ID

def test_warning_log_query():
    from warning_db import WarningDB
    db = WarningDB(":memory:")
    db.init()
    db.insert("企业A", "source1", "red", "舆情", "标题1", "", "", "")
    db.insert("企业B", "source2", "yellow", "金融", "标题2", "", "", "")
    rows = db.list_warnings(limit=10)
    assert len(rows) == 2

def test_ack_warning():
    from warning_db import WarningDB
    db = WarningDB(":memory:")
    db.init()
    wid = db.insert("企业A", "s", "red", "c", "标题", "", "", "")
    db.ack(wid, "测试员")
    row = db.get(wid)
    assert row["status"] == "acked"
    assert row["acked_by"] == "测试员"
```

- [ ] **步骤 2: 运行测试验证失败**

```bash
cd backend && python -m pytest src/tests/unit/test_warning_db.py -v
```
预期：全部 FAIL，报 ModuleNotFoundError

- [ ] **步骤 3: 编写实现代码**

```python
# backend/src/warning_db.py
import json
import sqlite3
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional


class WarningDB:
    """预警日志数据库（SQLite WAL 模式）。"""

    def __init__(self, db_path: str = "postloan.db"):
        self._path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA busy_timeout=5000;")
        return self._conn

    def init(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS warning_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enterprise TEXT NOT NULL,
                source TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT DEFAULT '',
                title TEXT NOT NULL,
                detail TEXT DEFAULT '',
                suggested_action TEXT DEFAULT '',
                content_hash TEXT UNIQUE,
                status TEXT DEFAULT 'new',
                acked_by TEXT DEFAULT '',
                acked_at TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                raw_data TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_w_enterprise ON warning_log(enterprise);
            CREATE INDEX IF NOT EXISTS idx_w_severity ON warning_log(severity);
            CREATE INDEX IF NOT EXISTS idx_w_status ON warning_log(status);
            CREATE INDEX IF NOT EXISTS idx_w_created ON warning_log(created_at);
        """)
        conn.commit()

    def _compute_hash(self, enterprise: str, source: str, title: str) -> str:
        raw = f"{enterprise}|{source}|{title}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32]

    def insert(self, enterprise: str, source: str, severity: str,
               category: str, title: str, detail: str,
               suggested_action: str, raw_data: str = "") -> int:
        conn = self._get_conn()
        content_hash = self._compute_hash(enterprise, source, title)
        try:
            conn.execute("""
                INSERT INTO warning_log
                    (enterprise, source, severity, category, title,
                     detail, suggested_action, content_hash, raw_data)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (enterprise, source, severity, category, title,
                  detail, suggested_action, content_hash, raw_data))
            conn.commit()
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        except sqlite3.IntegrityError:
            # 去重：更新 created_at
            conn.execute("""
                UPDATE warning_log SET created_at = datetime('now','localtime')
                WHERE content_hash = ?
            """, (content_hash,))
            conn.commit()
            row = conn.execute(
                "SELECT id FROM warning_log WHERE content_hash = ?", (content_hash,)
            ).fetchone()
            return row[0] if row else 0

    def get(self, warning_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM warning_log WHERE id = ?", (warning_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_warnings(self, enterprise: str = "", severity: str = "",
                      status: str = "", limit: int = 50, offset: int = 0
                      ) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        where = ["1=1"]
        params: list = []
        if enterprise:
            where.append("enterprise = ?")
            params.append(enterprise)
        if severity:
            where.append("severity = ?")
            params.append(severity)
        if status:
            where.append("status = ?")
            params.append(status)
        sql = f"SELECT * FROM warning_log WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def ack(self, warning_id: int, acked_by: str):
        conn = self._get_conn()
        conn.execute("""
            UPDATE warning_log SET status = 'acked', acked_by = ?,
            acked_at = datetime('now','localtime') WHERE id = ?
        """, (acked_by, warning_id))
        conn.commit()

    def mark_false(self, warning_id: int, acked_by: str):
        conn = self._get_conn()
        conn.execute("""
            UPDATE warning_log SET status = 'false_positive', acked_by = ?,
            acked_at = datetime('now','localtime') WHERE id = ?
        """, (acked_by, warning_id))
        conn.commit()

    def stats(self) -> Dict[str, Any]:
        conn = self._get_conn()
        by_severity = conn.execute("""
            SELECT severity, COUNT(*) as cnt FROM warning_log GROUP BY severity
        """).fetchall()
        by_status = conn.execute("""
            SELECT status, COUNT(*) as cnt FROM warning_log GROUP BY status
        """).fetchall()
        return {
            "by_severity": {r["severity"]: r["cnt"] for r in by_severity},
            "by_status": {r["status"]: r["cnt"] for r in by_status},
        }
```

- [ ] **步骤 4: 运行测试验证通过**

```bash
cd backend && PYTHONPATH=./src python -m pytest src/tests/unit/test_warning_db.py -v
```
预期：4 PASS

- [ ] **步骤 5: Commit**

---

### 任务 6: 创建 warning_collector.py

**文件：**
- 创建: `backend/src/services/warning_collector.py`

```python
"""Collector Agent — 多源并行采集调度器。"""
from __future__ import annotations
import asyncio
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger


@dataclass
class SourceResult:
    source: str
    status: str  # ok / timeout / error
    data: Optional[List[Dict[str, Any]]] = None
    error: str = ""


class CollectorService:
    """多源并行采集器。每个源独立执行，互不影响。"""

    def __init__(self, config):
        self._config = config
        self._enterprises = self._load_enterprises()

    @staticmethod
    def _load_enterprises() -> List[Dict[str, Any]]:
        path = Path(__file__).resolve().parent.parent.parent / "config" / "enterprises.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("enterprises", [])

    async def collect_all(self) -> List[SourceResult]:
        """并行采集所有数据源。"""
        tasks = []
        tasks.append(self._collect_qichacha())
        tasks.append(self._collect_ths())
        tasks.append(self._collect_web_search())
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, SourceResult)]

    async def _collect_qichacha(self) -> SourceResult:
        try:
            from services.qichacha_mcp import call_tool
            results = []
            for ent in self._enterprises:
                r = call_tool("risk", "get_company_risk_scan", {"searchKey": ent["name"]})
                if r:
                    results.append({"enterprise": ent["name"], "source": "qichacha", "raw": r})
            return SourceResult("qichacha", "ok", results)
        except Exception as e:
            logger.warning(f"[Collector] Qichacha failed: {e}")
            return SourceResult("qichacha", "error", error=str(e))

    async def _collect_ths(self) -> SourceResult:
        try:
            from iFinDPy import THS_iFinDLogin, THS_RQ, THS_iFinDLogout
            THS_iFinDLogin(self._config.ths_username, self._config.ths_password)
            results = []
            for ent in self._enterprises:
                code = ent.get("stock_code", "")
                concept = ent.get("concept_code", "")
                if code:
                    data = THS_RQ(code, "latest;changeRatio;pe;pb;totalMarketCap", "")
                    if data and data.errorcode == 0:
                        results.append({"enterprise": ent["name"], "source": "ths", "code": code,
                                        "latest": float(data.data.iloc[0]["latest"]),
                                        "changeRatio": float(data.data.iloc[0]["changeRatio"])})
                if concept:
                    data = THS_RQ(concept, "latest;changeRatio", "")
                    if data and data.errorcode == 0:
                        results.append({"enterprise": ent["name"], "source": "ths_concept",
                                        "code": concept, "latest": float(data.data.iloc[0]["latest"]),
                                        "changeRatio": float(data.data.iloc[0]["changeRatio"])})
            THS_iFinDLogout()
            return SourceResult("ths", "ok", results)
        except Exception as e:
            logger.warning(f"[Collector] THS failed: {e}")
            return SourceResult("ths", "error", error=str(e))

    async def _collect_web_search(self) -> SourceResult:
        try:
            from services.web_search import web_search
            results = []
            for ent in self._enterprises:
                query = f"\"{ent['name']}\" 风险 OR 违约 OR 诉讼 OR 处罚 OR 事故"
                r = web_search(query)
                if r:
                    results.append({"enterprise": ent["name"], "source": "web_search", "query": query,
                                    "results_count": len(r)})
            return SourceResult("web_search", "ok", results)
        except Exception as e:
            logger.warning(f"[Collector] WebSearch failed: {e}")
            return SourceResult("web_search", "error", error=str(e))
```

---

### 任务 7: 创建 warning_classifier.py

**文件：**
- 创建: `backend/src/services/warning_classifier.py`
- 创建: `backend/src/tests/unit/test_warning_classifier.py`

- [ ] **步骤 1: 编写失败的测试**

```python
# backend/src/tests/unit/test_warning_classifier.py
from services.warning_classifier import ClassifierService

def test_l1_fatal_direct_red():
    svc = ClassifierService()
    result = svc.classify("四川振海发生重大事故，3人死亡")
    assert result["severity"] == "red"

def test_l1_severe_to_l2():
    svc = ClassifierService()
    result = svc.classify("该公司被法院冻结资产")
    assert result["severity"] in ("red", "orange", "yellow")

def test_l1_no_keyword_returns_none():
    svc = ClassifierService()
    result = svc.classify("公司今天正常营业")
    assert result["severity"] == "none"
```

- [ ] **步骤 2: 运行测试验证失败**

```bash
cd backend && PYTHONPATH=./src python -m pytest src/tests/unit/test_warning_classifier.py -v
```
预期：FAIL

- [ ] **步骤 3: 编写实现代码**

```python
"""Classifier Agent — L1关键词预筛 + L2 LLM精细分级。"""
from __future__ import annotations
import json
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List
from loguru import logger


class ClassifierService:
    """两级分类器。"""

    def __init__(self, keywords_path: str = ""):
        path = keywords_path or str(
            Path(__file__).resolve().parent.parent.parent / "config" / "keywords.yaml"
        )
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self._fatal_keywords = [kw.lower() for kw in data.get("fatal", [])]
        self._severe_keywords = [kw.lower() for kw in data.get("severe", [])]
        self._watch_keywords = [kw.lower() for kw in data.get("watch", [])]

    def classify(self, text: str, enterprise: str = "",
                 do_l2: bool = True) -> Dict[str, Any]:
        """分类信号。返回 {severity, category, title, detail, suggested_action}。"""
        default = {
            "severity": "none", "category": "", "title": text[:100],
            "detail": text[:500], "suggested_action": ""
        }
        if not text.strip():
            return default

        text_lower = text.lower()

        # L1: 致命词 → 直接红色
        for kw in self._fatal_keywords:
            if kw in text_lower:
                return {**default, "severity": "red", "category": "安全/法律",
                        "title": f"致命词匹配: {kw}", "detail": text[:500],
                        "suggested_action": "立即核实，启动风险应对流程"}

        # L1: 严重/关注词 → 进入 L2
        has_severe = any(kw in text_lower for kw in self._severe_keywords)
        has_watch = any(kw in text_lower for kw in self._watch_keywords)

        if not has_severe and not has_watch:
            return default

        if do_l2:
            return self._l2_classify(text, enterprise, "orange" if has_severe else "yellow")

        return {**default, "severity": "orange" if has_severe else "yellow",
                "title": f"关键词匹配", "detail": text[:500]}

    def _l2_classify(self, text: str, enterprise: str,
                     l1_severity: str) -> Dict[str, Any]:
        """LLM 精细分级。"""
        try:
            from core.llm import invoke_llm
            from config import Configuration

            prompt = f"""你是贷后风险分析师。对企业信号进行分级。

企业: {enterprise}
信号内容: {text[:1000]}
L1预分级: {l1_severity}

请以JSON返回分级结果:
{{"severity": "red|orange|yellow|none",
  "category": "舆情|金融|经营|法律|安全",
  "title": "一句话标题",
  "detail": "详细说明",
  "suggested_action": "建议措施"}}

分级标准:
- red: 可能直接导致贷款损失(违约/查封/死亡)
- orange: 偿付能力显著恶化(评级下调/大额诉讼)
- yellow: 需要关注但不紧急
- none: 误报
"""
            config = Configuration.from_env()
            resp = invoke_llm(config, prompt, "", timeout=15)
            # 提取JSON
            match = re.search(r'\{[^{}]*\}', resp)
            if match:
                return json.loads(match.group(0))
            return {"severity": l1_severity, "category": "",
                    "title": text[:100], "detail": text[:500],
                    "suggested_action": ""}
        except Exception as e:
            logger.warning(f"L2 classify failed: {e}, fallback to L1 severity")
            return {"severity": l1_severity, "category": "",
                    "title": text[:100], "detail": text[:500],
                    "suggested_action": ""}
```

- [ ] **步骤 4: 运行测试验证通过**

```bash
cd backend && PYTHONPATH=./src python -m pytest src/tests/unit/test_warning_classifier.py -v
```
预期：3 PASS

- [ ] **步骤 5: Commit**

---

### 任务 8: 创建 warning API 路由 + 认证 + 调度器启动

**文件：**
- 修改: `backend/src/main.py`

```python
# 在 create_app() 中新增

# ── 预警 API ─────────────────────────────────

API_KEY = os.getenv("WARNING_API_KEY", "")

def _check_auth(request):
    """简单 API Key 认证。"""
    if API_KEY and request.headers.get("X-API-Key") != API_KEY:
        raise HTTPException(401, "Invalid API key")

@app.get("/api/warnings")
def list_warnings(enterprise: str = "", severity: str = "",
                  status: str = "", limit: int = 50, offset: int = 0,
                  request = None):
    _check_auth(request)
    from warning_db import WarningDB
    db = WarningDB()
    return {"warnings": db.list_warnings(enterprise, severity, status, limit, offset)}

@app.get("/api/warnings/{warning_id}")
def get_warning(warning_id: int, request = None):
    _check_auth(request)
    from warning_db import WarningDB
    row = WarningDB().get(warning_id)
    if not row:
        raise HTTPException(404)
    return row

@app.put("/api/warnings/{warning_id}/ack")
def ack_warning(warning_id: int, request = None):
    _check_auth(request)
    from warning_db import WarningDB
    WarningDB().ack(warning_id, "system")
    return {"status": "ok"}

@app.put("/api/warnings/{warning_id}/false")
def false_warning(warning_id: int, request = None):
    _check_auth(request)
    from warning_db import WarningDB
    WarningDB().mark_false(warning_id, "system")
    return {"status": "ok"}

@app.get("/api/warnings/stats")
def warning_stats(request = None):
    _check_auth(request)
    from warning_db import WarningDB
    return WarningDB().stats()

# ── 调度器启动 ─────────────────────────────────

from apscheduler.schedulers.background import BackgroundScheduler

_scheduler = BackgroundScheduler()

def _warning_collect_cycle():
    """预警采集-分类-推送完整周期。"""
    import asyncio
    from services.warning_collector import CollectorService
    from services.warning_classifier import ClassifierService
    from warning_db import WarningDB
    from config import WarningConfig

    cfg = WarningConfig.from_env()
    collector = CollectorService(cfg)
    classifier = ClassifierService(cfg.keywords_path)
    db = WarningDB()
    db.init()

    async def _run():
        results = await collector.collect_all()
        for src_result in results:
            if src_result.status != "ok" or not src_result.data:
                continue
            for item in src_result.data:
                text = json.dumps(item, ensure_ascii=False)
                classification = classifier.classify(text, item.get("enterprise", ""))
                if classification["severity"] != "none":
                    db.insert(
                        enterprise=item.get("enterprise", ""),
                        source=item.get("source", src_result.source),
                        **{k: classification.get(k, "") for k in
                           ("severity", "category", "title", "detail", "suggested_action")},
                        raw_data=text
                    )

    asyncio.run(_run())

_scheduler.add_job(
    _warning_collect_cycle, 'interval',
    seconds=int(os.getenv("WARNING_CRON_INTERVAL", "300")),
    id="warning_collect"
)

@app.on_event("startup")
def start_scheduler():
    from warning_db import WarningDB
    WarningDB().init()
    cfg = WarningConfig.from_env()
    if cfg.enabled_sources and cfg.enabled_sources != "none":
        _scheduler.start()
        logger.info("Warning scheduler started")
```

- [ ] **步骤 1: 验证**

```bash
cd backend && PYTHONPATH=./src python -c "
from main import app
routes = [r.path for r in app.routes]
print([r for r in routes if 'warning' in r])
"
```
预期：5条 warning 路由

- [ ] **步骤 2: Commit**

---

## P2: 健壮性（后续任务）

### 任务 9: DM Playwright 客户端（隔离进程 + 健康检查）
### 任务 10: 飞书 Dispatcher  
### 任务 11: 前端预警中心页面
### 任务 12: 集成测试管线

---

**剩余任务将在 P0+P1 完成后继续。**
