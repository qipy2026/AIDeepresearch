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

    @app.get("/api/warnings/{warning_id}")
    def get_warning(warning_id: int):
        from warning_db import WarningDB
        row = WarningDB().get(warning_id)
        if not row:
            raise HTTPException(404, "Warning not found")
        return row

    @app.put("/api/warnings/{warning_id}/ack")
    def ack_warning(warning_id: int, request: Request):
        if _API_KEY and request.headers.get("X-API-Key") != _API_KEY:
            raise HTTPException(401, "Invalid API key")
        from warning_db import WarningDB
        WarningDB().ack(warning_id, "operator")
        return {"status": "ok"}

    @app.put("/api/warnings/{warning_id}/false")
    def false_warning(warning_id: int, request: Request):
        if _API_KEY and request.headers.get("X-API-Key") != _API_KEY:
            raise HTTPException(401, "Invalid API key")
        from warning_db import WarningDB
        WarningDB().mark_false(warning_id, "operator")
        return {"status": "ok"}

    @app.put("/api/warnings/{warning_id}/unack")
    def unack_warning(warning_id: int, request: Request):
        if _API_KEY and request.headers.get("X-API-Key") != _API_KEY:
            raise HTTPException(401, "Invalid API key")
        from warning_db import WarningDB
        WarningDB().reset_status(warning_id)
        return {"status": "ok"}

    # ── 预警调度器 ─────────────────────────────────────────
    from apscheduler.schedulers.background import BackgroundScheduler
    from config import WarningConfig

    _scheduler = BackgroundScheduler()

    def _collect_source(name: str, text: str, db, cls, ent_name: str, source: str):
        """统一采集-提取-分类-存储。"""
        if not text or not text.strip():
            return
        from services.warning_extractor import extract
        ex = extract(source, text)
        # 用提取后的可读文本做分类，而非原始JSON
        classifiable = ex.get("readable", ex.get("summary", text))
        c = cls.classify(classifiable, ent_name)
        if c["severity"] != "none":
            db.insert(
                enterprise=ent_name, source=source,
                severity=c["severity"],
                category=c.get("category", ""),
                title=ex.get("title", c.get("title", classifiable[:100])),
                detail=ex.get("abstract", ex.get("readable", classifiable[:500])),
                suggested_action=c.get("suggested_action", ""),
                raw_data=text[:2000],
            )
            # 红色预警 → 写入待推送标记（供 Dispatcher 使用）
            if c["severity"] == "red":
                logger.warning(
                    "🔴 RED ALERT: {} | {} | {}",
                    ent_name, c.get("title", ""), c.get("suggested_action", "")
                )

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

        # 企查查采集
        try:
            from services.qichacha_mcp import call_tool
            for ent in _ents:
                r = call_tool("risk", "get_company_risk_scan", {"searchKey": ent["name"]})
                if r:
                    for item in r.get("content", []):
                        _collect_source("qichacha", item.get("text", ""),
                                        db, cls, ent["name"], "qichacha")
        except Exception as e:
            logger.warning(f"[collector] Qichacha failed: {e}")

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

    _scheduler.add_job(
        _warning_collect_cycle,
        "interval",
        seconds=int(_os.getenv("WARNING_CRON_INTERVAL", "300")),
        id="warning_collect",
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
