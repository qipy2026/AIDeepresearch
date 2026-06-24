"""FastAPI entrypoint exposing the DeepResearchAgent via HTTP."""

from __future__ import annotations

import json
import sys
from io import BytesIO

if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

from typing import Any, Dict, Iterator, Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from config import Configuration, SearchAPI
from agent import DeepResearchAgent

# 添加控制台日志处理程序
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>using_function:{function}</cyan> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)


# 添加错误日志文件处理程序
logger.add(
    sink=sys.stderr,
    level="ERROR",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>using_function:{function}</cyan> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)


class ResearchRequest(BaseModel):
    """Payload for triggering a research run."""

    topic: str = Field(..., description="Research topic supplied by the user")
    search_api: SearchAPI | None = Field(
        default=None,
        description="Override the default search backend configured via env",
    )


class ResearchResponse(BaseModel):
    """HTTP response containing the generated report and structured tasks."""

    report_markdown: str = Field(
        ..., description="Markdown-formatted research report including sections"
    )
    todo_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured TODO items with summaries and sources",
    )


class UploadReq(BaseModel):
    """RAG file upload request body."""
    enterprise: str
    content: str


def _mask_secret(value: Optional[str], visible: int = 4) -> str:
    """Mask sensitive tokens while keeping leading and trailing characters."""
    if not value:
        return "unset"

    if len(value) <= visible * 2:
        return "*" * len(value)

    return f"{value[:visible]}...{value[-visible:]}"


def _build_config(payload: ResearchRequest) -> Configuration:
    overrides: Dict[str, Any] = {}

    if payload.search_api is not None:
        overrides["search_api"] = payload.search_api

    return Configuration.from_env(overrides=overrides)


def create_app() -> FastAPI:
    app = FastAPI(title="AIDeepresearch")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 挂载 Vue SPA 静态文件（贷后助手）
    from fastapi.staticfiles import StaticFiles
    from pathlib import Path as _P
    _vue_dist = _P(__file__).parent.parent.parent / "frontend" / "dist"
    if _vue_dist.exists():
        app.mount("/app", StaticFiles(directory=str(_vue_dist), html=True), name="vue_spa")

    @app.on_event("startup")
    def log_startup_configuration() -> None:
        config = Configuration.from_env()

        if config.llm_provider == "ollama":
            base_url = config.sanitized_ollama_url()
        elif config.llm_provider == "lmstudio":
            base_url = config.lmstudio_base_url
        else:
            base_url = config.llm_base_url or "unset"

        logger.info(
            "DeepResearch configuration loaded: provider=%s model=%s base_url=%s search_api=%s "
            "max_loops=%s fetch_full_page=%s tool_calling=%s strip_thinking=%s api_key=%s "
            "llm_max_tokens=%s llm_max_retries=%s llm_timeout=%s",
            config.llm_provider,
            config.resolved_model() or "unset",
            base_url,
            (config.search_api.value if isinstance(config.search_api, SearchAPI) else config.search_api),
            config.max_web_research_loops,
            config.fetch_full_page,
            config.use_tool_calling,
            config.strip_thinking_tokens,
            _mask_secret(config.llm_api_key),
            config.llm_max_tokens,
            config.llm_max_retries,
            config.llm_timeout,
        )

    @app.get("/healthz")
    def health_check() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def root_redirect():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/warnings")

    @app.post("/research", response_model=ResearchResponse)
    def run_research(payload: ResearchRequest) -> ResearchResponse:
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config)
            result = agent.run(payload.topic)
        except ValueError as exc:  # Likely due to unsupported configuration
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive guardrail
            raise HTTPException(status_code=500, detail="Research failed") from exc

        todo_payload = [
            {
                "id": item.id,
                "title": item.title,
                "intent": item.intent,
                "query": item.query,
                "status": item.status,
                "summary": item.summary,
                "sources_summary": item.sources_summary,
                "note_id": item.note_id,
                "note_path": item.note_path,
            }
            for item in result.todo_items
        ]

        return ResearchResponse(
            report_markdown=(result.report_markdown or result.running_summary or ""),
            todo_items=todo_payload,
        )

    @app.post("/research/stream")
    def stream_research(payload: ResearchRequest) -> StreamingResponse:
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        def event_iterator() -> Iterator[str]:
            try:
                for event in agent.run_stream(payload.topic):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:  # pragma: no cover - defensive guardrail
                logger.exception("Streaming research failed")
                error_payload = {"type": "error", "detail": str(exc)}
                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    # ── RAG 文件上传路由 ─────────────────────────────────
    from pathlib import Path
    from services.rag_store import upload_text, list_enterprises, delete_enterprise
    from services.minio_storage import upload_bytes

    @app.get("/rag/upload", response_class=HTMLResponse)
    def rag_upload_page():
        html_path = Path(__file__).parent / "templates" / "upload.html"
        return html_path.read_text(encoding="utf-8")

    @app.post("/rag/upload")
    def rag_upload(req: UploadReq):
        if not req.enterprise.strip():
            raise HTTPException(400, "企业名称不能为空")
        if not req.content.strip():
            raise HTTPException(400, "文件内容不能为空")
        result = upload_text(req.content, req.enterprise.strip())
        return {"status": "ok", "enterprise": req.enterprise, "chunks": result["chunks"]}

    def _extract_text(content: bytes, filename: str) -> str:
        """根据文件后缀提取文本内容。"""
        name = filename.lower()
        if name.endswith(".docx"):
            from docx import Document
            doc = Document(BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs)
        elif name.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            return content.decode("utf-8", errors="replace")

    @app.post("/rag/upload/file")
    def rag_upload_file(
        enterprise: str = Form(...),
        file: UploadFile = File(...),
    ):
        if not enterprise.strip():
            raise HTTPException(400, "企业名称不能为空")
        raw = file.file.read()
        text = _extract_text(raw, file.filename or "upload")
        if not text.strip():
            raise HTTPException(400, "文件内容为空")
        # 保存到 MinIO（可选，失败不影响向量嵌入）
        object_name = f"{enterprise.strip()}/{file.filename or 'upload'}"
        try:
            upload_bytes(raw, object_name)
        except Exception:
            object_name = None
        # 嵌入向量库
        result = upload_text(text, enterprise.strip(), source=file.filename or "upload")
        resp = {"status": "ok", "enterprise": enterprise, "chunks": result["chunks"]}
        if object_name:
            resp["minio"] = object_name
        return resp

    @app.get("/rag/enterprises")
    def rag_enterprises():
        return {"enterprises": list_enterprises()}

    @app.delete("/rag/enterprise/{name:path}")
    def rag_delete_enterprise(name: str):
        delete_enterprise(name)
        return {"status": "ok", "enterprise": name}

    @app.get("/warnings", response_class=HTMLResponse)
    def warning_page():
        html_path = Path(__file__).parent / "templates" / "warnings.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/enterprises", response_class=HTMLResponse)
    def enterprises_page():
        html_path = Path(__file__).parent / "templates" / "enterprises.html"
        return html_path.read_text(encoding="utf-8")

    @app.get("/api/enterprises")
    def list_enterprises_api():
        import yaml as _yaml
        from pathlib import Path as _Path
        _p = _Path(__file__).parent.parent / "config" / "enterprises.yaml"
        with open(_p, "r", encoding="utf-8") as f:
            data = _yaml.safe_load(f)
        return {"enterprises": data.get("enterprises", [])}

    @app.post("/api/enterprises")
    async def add_enterprise_api(request: Request):
        import yaml as _yaml
        from pathlib import Path as _Path
        body = await request.json()
        keywords_raw = [k.strip() for k in body.get("keywords", "").split(",") if k.strip()]
        # 自动关键词：用户未填时从企业名称提取
        if not keywords_raw:
            import re as _re
            _core = _re.sub(r'(有限|有限责任|股份有限)?公司|（.*?）|\(.*?\)|分公司|办事处|服务有限公司', '', body.get("name", ""))
            keywords_raw = [_core.strip()] if _core.strip() else [body.get("name", "")]
        ent = {
            "name": body.get("name", ""),
            "role": body.get("role", "乙方"),
            "industry": body.get("industry", ""),
            "loan_amount": body.get("loan_amount", ""),
            "stock_code": body.get("stock_code", ""),
            "parent": body.get("parent", ""),
            "parent_stock_code": body.get("parent_stock_code", ""),
            "concept_code": body.get("concept_code", ""),
            "debtor": body.get("debtor", ""),
            "core_parties": body.get("core_parties", []),
            "keywords": keywords_raw,
        }
        if not ent["name"]:
            raise HTTPException(400, "企业名称不能为空")
        _p = _Path(__file__).parent.parent / "config" / "enterprises.yaml"
        with open(_p, "r", encoding="utf-8") as f:
            data = _yaml.safe_load(f)
        data["enterprises"].append(ent)
        with open(_p, "w", encoding="utf-8") as f:
            _yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return {"status": "ok", "enterprise": ent["name"]}

    # ── 行业扫描 API ──────────────────────────────────
    _industry_cache: dict[str, Any] = {}

    @app.get("/api/industry/sectors")
    def industry_sectors():
        """全行业扫描 + 企业池交叉匹配。"""
        try:
            from services.industry_scanner import scan_and_match
            import yaml as _yaml
            from pathlib import Path as _Path
            _ep = _Path(__file__).parent.parent / "config" / "enterprises.yaml"
            with open(_ep, "r", encoding="utf-8") as _f:
                _ents = _yaml.safe_load(_f).get("enterprises", [])
            result = scan_and_match(_ents)
            return {"status": "ok", **result}
        except Exception as _e:
            return {"status": "error", "message": str(_e)}

    # ── 原始素材 API ──────────────────────────────────
    @app.get("/api/scrape/sources")
    def scrape_sources(enterprise: str = "", limit: int = 100):
        """爬虫采集的原始素材列表，供人工审计。"""
        try:
            from scrape_db import list_sources
            rows = list_sources(enterprise, limit)
            return {"status": "ok", "sources": rows}
        except Exception as _e:
            return {"status": "error", "message": str(_e)}

    @app.post("/api/scrape/sources/{source_id}/credible")
    def scrape_mark_credible(source_id: int, credible: bool = True):
        """标记素材可信/不可信。"""
        try:
            from scrape_db import mark_credible
            mark_credible(source_id, credible)
            return {"status": "ok"}
        except Exception as _e:
            return {"status": "error", "message": str(_e)}

    # ── 数据源管理 ──────────────────────────────────

    @app.get("/sources", response_class=HTMLResponse)
    def sources_page():
        from pathlib import Path as _Path
        _p = _Path(__file__).parent / "templates" / "sources.html"
        return _p.read_text(encoding="utf-8")

    @app.get("/api/sources")
    def get_sources():
        import yaml as _yaml
        from pathlib import Path as _Path
        _p = _Path(__file__).parent.parent / "config" / "sources.yaml"
        with open(_p, "r", encoding="utf-8") as _f:
            data = _yaml.safe_load(_f)
        return {"status": "ok", "sources": data.get("sources", [])}

    @app.post("/api/sources")
    async def save_sources(request: Request):
        import yaml as _yaml
        from pathlib import Path as _Path
        body = await request.json()
        sources = body.get("sources", [])
        _p = _Path(__file__).parent.parent / "config" / "sources.yaml"
        with open(_p, "w", encoding="utf-8") as _f:
            _yaml.dump({"sources": sources}, _f, allow_unicode=True, default_flow_style=False)
        return {"status": "ok", "count": len(sources)}

    @app.delete("/api/enterprises/{name:path}")
    def delete_enterprise_api(name: str):
        import yaml as _yaml
        from pathlib import Path as _Path
        _p = _Path(__file__).parent.parent / "config" / "enterprises.yaml"
        with open(_p, "r", encoding="utf-8") as f:
            data = _yaml.safe_load(f)
        data["enterprises"] = [e for e in data.get("enterprises", []) if e["name"] != name]
        with open(_p, "w", encoding="utf-8") as f:
            _yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return {"status": "ok", "enterprise": name}

    # ── 预警中心 API ─────────────────────────────────────
    import os as _os

    _API_KEY = _os.getenv("WARNING_API_KEY", "")

    @app.get("/api/warnings")
    def list_warnings(
        enterprise: str = "",
        severity: str = "",
        status: str = "",
        limit: int = 50,
        offset: int = 0,
    ):
        from warning_db import WarningDB
        return {
            "warnings": WarningDB().list_warnings(
                enterprise, severity, status, limit, offset
            )
        }

    @app.get("/api/warnings/stats")
    def warning_stats():
        from warning_db import WarningDB
        return WarningDB().stats()

    @app.get("/api/warnings/factor")
    def query_factor(enterprise: str = "", tool: str = "", factor: str = ""):
        """快速查询单个风险因子明细。"""
        if not enterprise or not tool:
            raise HTTPException(400, "缺少 enterprise 或 tool 参数")
        from services.qichacha_mcp import call_tool
        import json as _json
        try:
            result = call_tool("risk", tool, {"searchKey": enterprise})
            if result:
                texts = []
                for item in result.get("content", []):
                    t = item.get("text", "")
                    if t and t.strip():
                        texts.append(t[:3000])
                return {
                    "enterprise": enterprise, "factor": factor, "tool": tool,
                    "content": "\n---\n".join(texts) if texts else "工具返回了空内容",
                    "raw": _json.dumps(result, ensure_ascii=False)[:2000] if not texts else "",
                }
            return {"enterprise": enterprise, "factor": factor, "tool": tool,
                    "content": "", "error": "call_tool 返回 None"}
        except Exception as e:
            return {"enterprise": enterprise, "factor": factor, "tool": tool,
                    "content": "", "error": str(e)}

    @app.get("/api/warnings/{warning_id}")
    def get_warning(warning_id: int):
        from warning_db import WarningDB
        row = WarningDB().get(warning_id)
        if not row:
            raise HTTPException(404, "Warning not found")
        return row

    @app.put("/api/warnings/{warning_id}/severity")
    async def set_warning_severity(warning_id: int, request: Request):
        """人工覆盖预警级别（红色可上调，黄色/橙色人工判断）。"""
        if _API_KEY and request.headers.get("X-API-Key") != _API_KEY:
            raise HTTPException(401, "Invalid API key")
        import json as _json
        body = await request.json()
        sev = body.get("severity", "")
        if sev not in ("red", "orange", "yellow"):
            raise HTTPException(400, f"Invalid severity: {sev}")
        from warning_db import WarningDB
        WarningDB().set_severity(warning_id, sev)
        return {"status": "ok", "severity": sev}

    @app.put("/api/warnings/{warning_id}/false")
    def false_warning(warning_id: int, request: Request):
        if _API_KEY and request.headers.get("X-API-Key") != _API_KEY:
            raise HTTPException(401, "Invalid API key")
        from warning_db import WarningDB
        WarningDB().mark_false(warning_id, "operator")
        return {"status": "ok"}

    @app.put("/api/warnings/{warning_id}/unfalse")
    def unfalse_warning(warning_id: int, request: Request):
        """撤销误报标记。"""
        if _API_KEY and request.headers.get("X-API-Key") != _API_KEY:
            raise HTTPException(401, "Invalid API key")
        from warning_db import WarningDB
        WarningDB().reset_status(warning_id)
        return {"status": "ok"}

    @app.get("/api/warnings/{warning_id}/detail")
    def get_warning_detail(warning_id: int):
        """钻取风险因子明细——调用企查查明细工具获取具体文书/案件内容。"""
        from warning_db import WarningDB
        import json as _json
        row = WarningDB().get(warning_id)
        if not row:
            raise HTTPException(404, "Warning not found")
        raw = row.get("raw_data", "")
        enterprise = row["enterprise"]

        # 解析企查查风险扫描结果
        factors = []
        details = []
        parse_error = None
        try:
            data = _json.loads(raw)
            scans = data.get("风险因子扫描", [])
            factors = [
                {"name": s.get("风险因子", ""), "count": s.get("条目数", 0),
                 "tool": s.get("明细工具", "")}
                for s in scans if s.get("条目数", 0) > 0
            ]
        except (_json.JSONDecodeError, TypeError) as e:
            parse_error = str(e)
            # JSON 解析失败时，展示原始数据供排查
            factors = [{"name": "原始数据（JSON解析失败）", "count": 0,
                        "tool": "", "raw_preview": raw[:1000]}]

        # 调用每个有记录的风险因子的明细工具
        if factors and not parse_error:
            from services.qichacha_mcp import call_tool
            for f in factors[:5]:
                try:
                    result = call_tool("risk", f["tool"],
                                       {"searchKey": enterprise})
                    if result:
                        texts = []
                        for item in result.get("content", []):
                            t = item.get("text", "")
                            if t and t.strip():
                                texts.append(t[:3000])
                        details.append({
                            "factor": f["name"],
                            "count": f["count"],
                            "tool_called": f["tool"],
                            "content": "\n---\n".join(texts) if texts else "工具返回了空内容",
                            "raw_response": _json.dumps(result, ensure_ascii=False)[:2000] if not texts else "",
                        })
                    else:
                        details.append({
                            "factor": f["name"], "count": f["count"],
                            "tool_called": f["tool"],
                            "content": "",
                            "error": "call_tool 返回 None（可能是网络或认证问题）",
                        })
                except Exception as e:
                    details.append({
                        "factor": f["name"], "count": f["count"],
                        "tool_called": f["tool"],
                        "content": "",
                        "error": str(e),
                    })

        return {
            "warning_id": warning_id,
            "enterprise": enterprise,
            "source": row["source"],
            "parse_error": parse_error,
            "factors": factors,
            "details": details,
        }

    @app.post("/api/warnings/{warning_id}/push")
    async def push_warning(warning_id: int, request: Request):
        """飞书交互卡片推送——支持点击跳转详情。"""
        if _API_KEY and request.headers.get("X-API-Key") != _API_KEY:
            raise HTTPException(401, "Invalid API key")
        body = await request.json()
        chat_id = body.get("chat_id", "") or _os.getenv("WARNING_FEISHU_CHAT_ID", "")
        if not chat_id:
            raise HTTPException(400, "未指定 chat_id，且未配置 WARNING_FEISHU_CHAT_ID")
        # 构建飞书交互卡片
        sev = body.get("severity", "orange")
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text",
                          "content": f"{'🔴' if sev=='red' else '🟠'} {'红色' if sev=='red' else '橙色'}预警: {body.get('enterprise','')}"},
                "template": "red" if sev == "red" else "orange",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**风险摘要**\n{body.get('summary','')}"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**建议措施**\n{body.get('action','')}"}},
                {"tag": "hr"},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "📋 查看详情"},
                     "type": "primary", "url": body.get("detail_url", "http://127.0.0.1:8080/warnings")},
                ]},
                {"tag": "note", "elements": [
                    {"tag": "plain_text", "content": "📡 企查查自动监测 · 贷后监管系统"},
                ]},
            ],
        }
        import subprocess, shutil, json as _json
        _lark = shutil.which("lark-cli") or "lark-cli"
        try:
            cmd = [_lark, "im", "+messages-send", "--as", "bot", "--chat-id", chat_id,
                   "--content", _json.dumps(card, ensure_ascii=False),
                   "--msg-type", "interactive", "--format", "json"]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=15)
            if result.returncode == 0:
                logger.info(f"飞书推送成功 → {chat_id}")
                return {"status": "ok", "chat_id": chat_id}
            return {"status": "failed", "detail": (result.stderr or result.stdout)[:300]}
        except subprocess.TimeoutExpired:
            return {"status": "failed", "detail": "推送超时"}
        except Exception as e:
            return {"status": "failed", "detail": str(e)}

    @app.get("/api/feishu/chats")
    def list_feishu_chats():
        """获取飞书可用群聊列表。"""
        import subprocess
        import shutil
        _lark = shutil.which("lark-cli") or "lark-cli"
        chats = []
        stdout_preview = ""
        try:
            result = subprocess.run(
                [_lark, "im", "+chat-list", "--as", "bot",
                 "--page-size", "50", "--format", "json"],
                capture_output=True, text=True, encoding="utf-8", timeout=10,
            )
            stdout_preview = (result.stdout or "")[:500]
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                # lark-cli 返回格式: {"ok":true, "data":{"chats":[...]}} 或 {"ok":true, "chats":[...]}
                raw = data.get("chats") or (data.get("data") or {}).get("chats") or []
                for item in raw:
                    chats.append({
                        "chat_id": item.get("chat_id", ""),
                        "name": item.get("name", "") or item.get("chat_id", ""),
                    })
        except Exception as e:
            logger.warning(f"Feishu chat list failed: {e}, stdout: {stdout_preview}")
        default_chat = _os.getenv("WARNING_FEISHU_CHAT_ID", "")
        if default_chat and not any(c["chat_id"] == default_chat for c in chats):
            chats.insert(0, {"chat_id": default_chat, "name": f"默认群 ({default_chat[:16]}...)"})
        return {"chats": chats, "hint": "bot无法列举群聊，请手动输入chat_id或配置WARNING_FEISHU_CHAT_ID"}

    @app.post("/api/warnings/collect")
    def trigger_collect(request: Request):
        if _API_KEY and request.headers.get("X-API-Key") != _API_KEY:
            raise HTTPException(401, "Invalid API key")
        from warning_db import WarningDB
        before = len(WarningDB().list_warnings(limit=1000))
        _warning_collect_cycle()
        after = len(WarningDB().list_warnings(limit=1000))
        return {"status": "ok", "before": before, "after": after, "new": after - before}

    # ── 预警调度器 ─────────────────────────────────────────
    from apscheduler.schedulers.background import BackgroundScheduler
    from config import WarningConfig

    _scheduler = BackgroundScheduler()

    def _collect_source(name: str, text: str, db, cls, ent_name: str, source: str,
                        title_override: str = "", detail_override: str = "",
                        source_url: str = ""):
        """统一采集-提取-分类-存储。"""
        if not text or not text.strip():
            return
        from services.warning_extractor import extract
        ex = extract(source, text)
        classifiable = ex.get("readable", ex.get("summary", text))
        c = cls.classify(classifiable, ent_name)
        sev = c["severity"] if c["severity"] != "none" else "normal"
        title = title_override or ex.get("title") or c.get("title") or classifiable[:100]
        detail = detail_override or ex.get("summary") or ex.get("readable") or classifiable[:500]
        db.insert(
            enterprise=ent_name, source=source,
            severity=sev,
            category=c.get("category", ""),
            title=title,
            detail=detail,
            suggested_action=c.get("suggested_action", ""),
            raw_data=text,
            source_url=source_url,
            )
            # 不再自动推送——由用户在预警中心点击"推送"手动发送

    def _warning_collect_cycle():
        """预警采集→分类→存储完整周期。"""
        from services.warning_classifier import ClassifierService
        from warning_db import WarningDB
        import yaml as _yaml
        from pathlib import Path as _Path

        cfg = WarningConfig.from_env()
        if not cfg.enabled_sources or cfg.enabled_sources == "none":
            return
        db = WarningDB()
        db.init()
        cls = ClassifierService(cfg.keywords_path)
        _ep = _Path(__file__).resolve().parent.parent / "config" / "enterprises.yaml"
        with open(_ep, "r", encoding="utf-8") as _f:
            _ents = _yaml.safe_load(_f).get("enterprises", [])

        # 采集：乙方企查查，甲方+母公司企查查+同花顺
        try:
            from services.qichacha_mcp import call_tool
            import json as _json
            seen_parents = set()
            for ent in _ents:
                role = ent.get("role", "乙方")
                # 1. 企查查查询企业自身
                r = call_tool("risk", "get_company_risk_scan", {"searchKey": ent["name"]})
                has_risk = False
                if r:
                    label = f"{ent['name']}（{role}）"
                    for item in r.get("content", []):
                        _collect_source("qichacha", item.get("text", ""),
                                        db, cls, label, "qichacha")
                    try:
                        data = _json.loads(r.get("content",[{}])[0].get("text","{}"))
                        has_risk = data.get("有记录因子数", 0) > 0
                    except: pass

                # 2. 同花顺全量采集：行情+异常+财务+问财+概念
                try:
                    from services.ths_collector import collect_all
                    signals = collect_all(
                        cfg.ths_username, cfg.ths_password,
                        stock_code=ent.get("parent_stock_code", "") or ent.get("stock_code", ""),
                        enterprise=ent.get("parent", "") or ent["name"],
                        industry=ent.get("industry", ""),
                        concept_code=ent.get("concept_code", ""),
                    )
                    for sig in signals:
                        _collect_source(sig["source"],
                            sig.get("raw", sig.get("detail", "")),
                            db, cls,
                            sig.get("label", ent["name"]),
                            sig.get("source", "ths_stock"),
                            title_override=sig.get("title", ""),
                            detail_override=sig.get("detail", ""))
                except Exception as e:
                    logger.warning(f"THS collect failed for {ent['name']}: {e}")

                # 3. 甲方无信号 → 追溯母公司企查查
                if role == "甲方" and ent.get("parent"):
                    parent_name = ent["parent"]
                    if parent_name not in seen_parents and not has_risk:
                        seen_parents.add(parent_name)
                        r2 = call_tool("risk", "get_company_risk_scan",
                                       {"searchKey": parent_name})
                        if r2:
                            for item in r2.get("content", []):
                                _collect_source("qichacha", item.get("text", ""),
                                                db, cls,
                                                f"{parent_name}（{ent['name']}的母公司）",
                                                "qichacha")
        except Exception as e:
            logger.warning(f"[collector] Qichacha/THS failed: {e}")

        # 网页爬虫采集（巨潮公告等）
        try:
            from services.web_scraper import collect_for_enterprise, collect_from_sources
            from services.llm_extractor import extract_and_classify, classify_to_severity
            from scrape_db import insert as insert_scrape_source
            for ent in _ents:
                scraped = collect_for_enterprise(ent)
                scraped += collect_from_sources(ent)
                for item in scraped:
                    llm_result = extract_and_classify(item["text"], _ents)
                    # 存储原始素材（无论是否关联到企业都存）
                    direction = ""
                    summary = ""
                    if not llm_result.get("irrelevant") and llm_result.get("relevant_enterprises"):
                        direction = llm_result["relevant_enterprises"][0].get("direction", "")
                        summary = llm_result["relevant_enterprises"][0].get("summary", "")
                    insert_scrape_source(
                        ent.get("parent", "") or ent["name"],
                        item.get("source", "web"),
                        item.get("source_url", ""),
                        item["title"],
                        item["text"][:5000],
                        direction,
                        summary,
                    )
                    if llm_result.get("irrelevant"):
                        continue
                    for rel in llm_result.get("relevant_enterprises", []):
                        sev = classify_to_severity(
                            rel.get("direction", "neutral"),
                            rel.get("confidence", 0.5))
                        _collect_source(
                            "web_scrape",
                            f'{item["title"]}\n\n{item["text"][:500]}\n\nLLM分析: {json.dumps(rel, ensure_ascii=False)}',
                            db, cls,
                            f'{ent.get("parent", "") or ent["name"]}（网页采集）',
                            "web_scrape",
                            title_override=rel.get("summary", item["title"]),
                            detail_override=f'[{rel.get("direction","")}] {rel.get("summary","")} (置信度{rel.get("confidence",0)})',
                            source_url=item.get("source_url", ""))
        except Exception as e:
            logger.warning(f"[collector] Web scraping failed: {e}")

        # 票交所 RAG 查询
        try:
            from services.rag_store import query as rag_query
            for ent in _ents:
                for kw in ["商票", "承兑", "逾期", "拒付", "票据"]:
                    result = rag_query(kw, ent["name"], n_results=1)
                    if result:
                        _collect_source("rag", result, db, cls, ent["name"], "piaojiaosuo")
        except Exception as e:
            logger.warning(f"[collector] Piaojiaosuo RAG failed: {e}")

        # Web Search 舆情查询
        try:
            from services.web_search import dispatch_search
            for ent in _ents:
                kw = ent.get("keywords", [ent["name"]])
                query = f'"{kw[0]}" 风险 OR 违约 OR 诉讼 OR 处罚 OR 事故'
                try:
                    results, _ = dispatch_search(query, Configuration.from_env(), 1)
                    if results:
                        text = "\n".join(
                            f"{r.get('title','')}: {r.get('snippet',r.get('body',''))}"[:300]
                            for r in results[:3]
                        )
                        if text.strip():
                            _collect_source("web_search", text, db, cls,
                                            ent["name"], "web_search")
                except: pass
        except Exception as e:
            logger.warning(f"[collector] WebSearch failed: {e}")

        # 同花顺 EDB 宏观数据（只查询一次，全局共享）
        try:
            from iFinDPy import THS_iFinDLogin, THS_EDB, THS_iFinDLogout
            THS_iFinDLogin(cfg.ths_username, cfg.ths_password)
            macro = THS_EDB("M001620326", "", "2026-01-01", "2026-06-30")
            if macro and macro.errorcode == 0 and macro.data is not None:
                gdp_row = macro.data.iloc[-1]
                macro_text = f"GDP最新值: {gdp_row.get('value', 'N/A')} (时间: {gdp_row.get('time', 'N/A')})"
                _collect_source("ths_macro", macro_text, db, cls,
                                "宏观经济", "ths_macro")
            THS_iFinDLogout()
        except Exception as e:
            logger.debug(f"[collector] THS macro failed: {e}")

    _scheduler.add_job(
        _warning_collect_cycle,
        "interval",
        seconds=int(_os.getenv("WARNING_CRON_INTERVAL", "300")),
        id="warning_collect",
    )

    # 行业扫描定时任务（工作日 9:00 和 14:00）
    def _industry_scan_job():
        try:
            import yaml as _yaml
            from pathlib import Path as _Path
            from services.industry_scanner import scan_and_match
            _ep = _Path(__file__).parent.parent / "config" / "enterprises.yaml"
            with open(_ep, "r", encoding="utf-8") as _f:
                _ents = _yaml.safe_load(_f).get("enterprises", [])
            result = scan_and_match(_ents)
            logger.info("Industry scan: %d risks, %d opportunities",
                        len(result.get("matched_risks", [])),
                        len(result.get("missed_opportunities", [])))
        except Exception as _e:
            logger.warning("Industry scan failed: %s", _e)

    _industry_cron = _os.getenv("INDUSTRY_SCAN_CRON", "0 9,14 * * 1-5")
    _cron_parts = _industry_cron.split()
    if len(_cron_parts) == 5:
        _scheduler.add_job(
            _industry_scan_job,
            "cron",
            minute=_cron_parts[0], hour=_cron_parts[1],
            day=_cron_parts[2], month=_cron_parts[3],
            day_of_week=_cron_parts[4],
            id="industry_scan",
        )
    else:
        _scheduler.add_job(
            _industry_scan_job, "interval", hours=6, id="industry_scan"
        )

    @app.on_event("startup")
    def _start_warning_scheduler():
        from warning_db import WarningDB
        WarningDB().init()
        cfg = WarningConfig.from_env()
        if cfg.enabled_sources and cfg.enabled_sources != "none":
            _scheduler.start()
            logger.info("Warning scheduler started (interval={}s)", cfg.cron_interval)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    import os
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
        log_level="info"
    )
