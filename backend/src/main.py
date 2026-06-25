"""FastAPI entrypoint exposing the DeepResearchAgent via HTTP."""

from __future__ import annotations

import json
import os
import sys
import time
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
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
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
        # 旧路径 301 重定向 → /loan/（必须在 mount 之前注册，否则会被 SPA fallback 拦截）
        @app.get("/app/{path:path}")
        async def _redirect_app_legacy(path: str = ""):
            """重定向旧 /app/ 路径到 /loan/"""
            return RedirectResponse(url=f"/loan/{path}", status_code=301)

        @app.get("/warnings")
        async def _redirect_warnings():
            return RedirectResponse(url="/loan/warnings", status_code=301)

        @app.get("/enterprises")
        async def _redirect_enterprises():
            return RedirectResponse(url="/loan/", status_code=301)

        @app.get("/sources")
        async def _redirect_sources():
            return RedirectResponse(url="/loan/sources", status_code=301)

        @app.get("/rag/upload")
        async def _redirect_upload():
            return RedirectResponse(url="/loan/upload", status_code=301)

        @app.get("/reports")
        async def _redirect_reports():
            return RedirectResponse(url="/loan/reports", status_code=301)

        @app.get("/reports-edit")
        async def _redirect_reports_edit():
            return RedirectResponse(url="/loan/reports", status_code=301)

        app.mount("/loan", StaticFiles(directory=str(_vue_dist), html=True), name="vue_spa")

    # 快照图片静态路由（从 search 项目复制到本地的摄像头快照）
    _snapshot_dir = _P(__file__).parent.parent / os.getenv("CAMERA_SNAPSHOT_LOCAL", "snapshot_data")
    _snapshot_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/snapshots/{filename}")
    def serve_snapshot(filename: str):
        """Serve local snapshot images (copied from search project)."""
        from fastapi.responses import FileResponse
        file_path = _snapshot_dir / filename
        if not file_path.exists():
            raise HTTPException(404, f"Snapshot not found: {filename}")
        return FileResponse(str(file_path))

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

    # ── 按需采集 + 数据新鲜度门控 ─────────────────────────

    def _collect_single_enterprise(enterprise_name: str):
        """对单个企业执行快速采集（企查查+同花顺+百度舆情），在文件锁保护下运行。"""
        import yaml as _yaml
        from pathlib import Path as _Path

        _ep = _Path(__file__).resolve().parent.parent / "config" / "enterprises.yaml"
        with open(_ep, "r", encoding="utf-8") as _f:
            _ents = _yaml.safe_load(_f).get("enterprises", [])
        ent = next((e for e in _ents if e["name"] == enterprise_name), None)
        if not ent:
            logger.warning("_collect_single_enterprise: %s not found", enterprise_name)
            return

        lock_fd = _acquire_collection_lock(timeout=30)
        if lock_fd is None:
            logger.info("On-demand collect skipped: lock held by scheduled cycle")
            return

        try:
            from services.warning_classifier import ClassifierService
            from warning_db import WarningDB
            cfg = WarningConfig.from_env()
            db = WarningDB()
            db.init()
            cls = ClassifierService(cfg.keywords_path)

            # 1. 企查查风险扫描
            try:
                from services.qichacha_mcp import call_tool
                import json as _json
                r = call_tool("risk", "get_company_risk_scan",
                              {"searchKey": ent["name"]})
                if r:
                    for item in r.get("content", []):
                        _collect_source("qichacha", item.get("text", ""),
                                        db, cls, ent["name"], "qichacha")
            except Exception as e:
                logger.warning("On-demand qichacha failed: %s", e)

            # 2. 同花顺采集
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
                logger.warning("On-demand THS failed: %s", e)

            # 3. 百度舆情搜索
            try:
                from services.web_search import _search_baidu
                SENTIMENT_QUERIES = [
                    "{name} 投诉 OR 曝光 OR 维权",
                    "{name} 拖欠 OR 违约 OR 烂尾",
                    "{name} 负面 新闻",
                    "{name} 事故 OR 安全",
                    "{name} 维权 OR 讨薪",
                    "{name} 监管 OR 处罚 OR 约谈",
                    "{name} 破产 OR 重整",
                ]
                for tmpl in SENTIMENT_QUERIES:
                    q = tmpl.format(name=ent["name"])
                    try:
                        for r in _search_baidu(q, max_results=3):
                            _collect_source("baidu_search",
                                f"{r.get('title','')}\n{r.get('content','')}",
                                db, cls, ent["name"], "baidu_search",
                                title_override=r.get("title",""),
                                source_url=r.get("url",""))
                    except Exception:
                        pass
            except Exception as e:
                logger.warning("On-demand Baidu failed: %s", e)

            logger.info("On-demand collect completed for %s", enterprise_name)
        finally:
            _release_collection_lock(lock_fd)

    def _ensure_data_freshness(enterprise_name: str) -> str:
        """检查数据新鲜度，不足则触发后台按需采集+轮询。
        返回: 'fresh' | 'stale' | 'empty'
        """
        from warning_db import WarningDB
        import threading

        db = WarningDB()
        recent_24h = db.count_recent_warnings(enterprise_name, hours=24)
        if recent_24h >= 3:
            return "fresh"

        recent_72h = db.count_recent_warnings(enterprise_name, hours=72)
        if recent_72h >= 3:
            return "stale"

        # 后台触发按需采集
        logger.info("Data stale for %s (24h:%d, 72h:%d), triggering on-demand collect",
                    enterprise_name, recent_24h, recent_72h)
        t = threading.Thread(target=_collect_single_enterprise,
                             args=(enterprise_name,), daemon=True)
        t.start()

        # 轮询等待（最多 30 秒）
        for _ in range(10):
            time.sleep(3)
            if db.count_recent_warnings(enterprise_name, hours=24) >= 3:
                return "fresh"

        logger.warning("On-demand collect timeout for %s", enterprise_name)
        return "empty"

    @app.post("/research", response_model=ResearchResponse)
    def run_research(payload: ResearchRequest) -> ResearchResponse:
        # Phase 0: 数据新鲜度门控
        # 从 topic 中尝试提取企业名（格式: "企业名 周报/月报" 或直接是企业名）
        import re as _re
        _topic = payload.topic.strip()
        _ent_match = _re.match(r"^(.+?)(?:周报|月报|年报|风险|监测|报告|\s|$)", _topic)
        _enterprise = _ent_match.group(1).strip() if _ent_match else _topic

        freshness = _ensure_data_freshness(_enterprise)
        if freshness == "empty":
            raise HTTPException(
                status_code=503,
                detail=f"「{_enterprise}」暂无足够预警数据，请稍后重试或手动触发采集 "
                       f"POST /api/warnings/collect")
        elif freshness == "stale":
            logger.info("Using stale data for %s", _enterprise)

        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config)
            result = agent.run(payload.topic)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
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

        # Tier 1 自动补全：行业或关键词为空时，LLM 推断
        enrichment = None
        if not ent["industry"] or not keywords_raw or len(keywords_raw) <= 1:
            try:
                from services.enterprise_enricher import enrich
                enrichment = enrich(ent["name"], ent["role"])
                if not enrichment.get("skipped"):
                    if enrichment.get("industry") and not ent["industry"]:
                        ent["industry"] = enrichment["industry"]
                    if enrichment.get("keywords"):
                        ent["keywords"] = enrichment["keywords"]
            except Exception as _e:
                logger.warning("enricher failed for %s: %s", ent["name"], _e)

        _p = _Path(__file__).parent.parent / "config" / "enterprises.yaml"
        with open(_p, "r", encoding="utf-8") as f:
            data = _yaml.safe_load(f)
        data["enterprises"].append(ent)
        with open(_p, "w", encoding="utf-8") as f:
            _yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        resp = {"status": "ok", "enterprise": ent["name"]}
        if enrichment:
            resp["enrichment"] = {
                "industry": enrichment.get("industry"),
                "keywords": enrichment.get("keywords"),
                "confidence": enrichment.get("confidence"),
                "skipped": enrichment.get("skipped", False),
            }
        return resp

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

    # ── 报告管理 ──────────────────────────────────
    import glob as _glob
    from datetime import datetime as _dt
    from pathlib import Path as _RP

    _reports_dir = _RP(__file__).parent.parent / "reports"
    _reports_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/reports", response_class=HTMLResponse)
    def reports_page():
        _p = _RP(__file__).parent / "templates" / "reports.html"
        return _p.read_text(encoding="utf-8") if _p.exists() else "<h1>reports.html not found</h1>"

    @app.get("/reports-edit", response_class=HTMLResponse)
    def reports_edit_page():
        _p = _RP(__file__).parent / "templates" / "reports-edit.html"
        return _p.read_text(encoding="utf-8") if _p.exists() else "<h1>reports-edit.html not found</h1>"

    @app.get("/api/reports")
    def list_reports():
        files = sorted(_glob.glob(str(_reports_dir / "*.md")), reverse=True)
        result = []
        for f in files:
            name = _RP(f).stem.replace("_", " ")[:60]
            mtime = _RP(f).stat().st_mtime
            result.append({
                "id": _RP(f).stem,
                "name": name,
                "updated": _dt.fromtimestamp(mtime).isoformat(),
                "size": _RP(f).stat().st_size,
            })
        return {"status": "ok", "reports": result}

    @app.get("/api/reports/{report_id}")
    def get_report(report_id: str):
        _p = _reports_dir / f"{report_id}.md"
        if not _p.exists():
            raise HTTPException(404, "Report not found")
        content = _p.read_text(encoding="utf-8")
        # 从文件名解析标题（格式: {title}_{timestamp}）
        title = _p.stem
        # 尝试去掉末尾的时间戳后缀
        import re as _re
        _title_match = _re.match(r"^(.+)_\d{8}_\d{6}$", title)
        if _title_match:
            title = _title_match.group(1).replace("_", " ")
        else:
            title = title.replace("_", " ")
        return {"status": "ok", "id": report_id, "title": title, "content": content}

    @app.post("/api/reports")
    async def save_report(request: Request):
        body = await request.json()
        title = body.get("title", "untitled")[:80]
        content = body.get("content", "")
        safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in title)
        filename = f"{safe}_{_dt.now().strftime('%Y%m%d_%H%M%S')}.md"
        _p = _reports_dir / filename
        _p.write_text(content, encoding="utf-8")
        return {"status": "ok", "id": _p.stem, "filename": filename}

    @app.put("/api/reports/{report_id}")
    async def update_report(report_id: str, request: Request):
        """更新已有报告——title 变更时同步更新文件名和 # heading。"""
        _p = _reports_dir / f"{report_id}.md"
        if not _p.exists():
            raise HTTPException(404, "Report not found")
        body = await request.json()
        new_title = body.get("title", "")[:80]
        new_content = body.get("content", "")
        if not new_content.strip():
            raise HTTPException(400, "Content cannot be empty")

        # 如果 title 变了，更新文件名（保留时间戳后缀）
        import re as _re
        _ts_match = _re.search(r"_(\d{8}_\d{6})$", report_id)
        _ts_suffix = _ts_match.group(1) if _ts_match else _dt.now().strftime('%Y%m%d_%H%M%S')
        if new_title:
            safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in new_title)
            new_filename = f"{safe}_{_ts_suffix}.md"
            new_p = _reports_dir / new_filename
            if new_p != _p:
                _p.rename(new_p)
                _p = new_p

        # 更新 markdown 中的第一个 # heading
        import re as _re2
        if new_title and new_content.startswith("# "):
            new_content = _re2.sub(r"^# .+", f"# {new_title}", new_content, count=1)

        _p.write_text(new_content, encoding="utf-8")
        return {"status": "ok", "id": _p.stem, "title": new_title}

    @app.post("/api/reports/{report_id}/send-to-feishu")
    async def send_report_to_feishu(report_id: str, request: Request):
        """发送报告 Markdown 到飞书群。复用 warning_dispatcher._send_markdown。"""
        _p = _reports_dir / f"{report_id}.md"
        if not _p.exists():
            raise HTTPException(404, "Report not found")

        body = await request.json()
        chat_id = body.get("chat_id", "")
        if not chat_id:
            raise HTTPException(400, "未指定 chat_id")

        content = _p.read_text(encoding="utf-8")
        from services.warning_dispatcher import _send_markdown

        # UTF-8 安全截断：4000 字节 → 段落边界
        _max_bytes = 4000
        _truncated = False
        if len(content.encode("utf-8")) > _max_bytes:
            _raw = content.encode("utf-8")[:_max_bytes]
            # errors='ignore' 自动丢弃末尾不完整的 UTF-8 序列
            _text = _raw.decode("utf-8", errors="ignore")
            # 向前扫描到最近的段落边界（双换行）
            _last_para = _text.rfind("\n\n")
            if _last_para > len(_text) // 2:
                _text = _text[:_last_para]
            # 拼接报告链接
            import os as _os
            _base_url = _os.getenv("BASE_URL", "http://127.0.0.1:8080")
            _text += f"\n\n---\n> [查看完整报告]({_base_url}/reports-edit?id={report_id})"
            content = _text
            _truncated = True

        success = _send_markdown(chat_id, content)
        if success:
            return {"status": "ok", "chat_id": chat_id, "truncated": _truncated}
        return {"status": "failed", "detail": "lark-cli 发送失败", "truncated": _truncated}

    @app.delete("/api/reports/{report_id}")
    def delete_report(report_id: str):
        _p = _reports_dir / f"{report_id}.md"
        if _p.exists():
            _p.unlink()
        return {"status": "ok"}

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

    # ── 文件锁（跨 worker 互斥，防止多进程重复采集）────────
    import tempfile as _tempfile
    _COLLECTION_LOCK_FILE = os.path.join(_tempfile.gettempdir(), "aidr_collection.lock")

    def _acquire_collection_lock(timeout: int = 10):
        """跨平台文件锁。返回锁文件 fd，获取失败返回 None。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                fd = os.open(_COLLECTION_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(fd, str(os.getpid()).encode())
                return fd
            except FileExistsError:
                time.sleep(0.5)
        return None

    def _release_collection_lock(fd):
        """释放文件锁。"""
        if fd is not None:
            try:
                os.close(fd)
                os.unlink(_COLLECTION_LOCK_FILE)
            except OSError:
                pass

    def _collect_source(name: str, text: str, db, cls, ent_name: str, source: str,
                        title_override: str = "", detail_override: str = "",
                        source_url: str = ""):
        """统一采集-提取-分类-存储。"""
        if not text or not text.strip():
            return
        # 企查查搜索无匹配=企业不存在，不生成预警
        if source == 'qichacha' and '未匹配到搜索关键词' in text:
            logger.info(f'qichacha: enterprise not found for {ent_name}, skip')
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

        # 文件锁：防止多 worker 重复采集
        lock_fd = _acquire_collection_lock(timeout=5)
        if lock_fd is None:
            logger.info("Collection lock held by another worker, skipping cycle")
            return

        try:
            _run_collection_cycle(cfg)
        finally:
            _release_collection_lock(lock_fd)

    def _run_collection_cycle(cfg):
        """采集周期主逻辑（在文件锁保护下执行）。"""
        from services.warning_classifier import ClassifierService
        from warning_db import WarningDB
        import yaml as _yaml
        from pathlib import Path as _Path

        db = WarningDB()
        db.init()
        _keywords_path = cfg.keywords_path
        if not _Path(_keywords_path).is_absolute():
            _keywords_path = str(_Path(__file__).resolve().parent.parent / _keywords_path)
        cls = ClassifierService(_keywords_path)
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

        # Phase 3: 定向采集（东方财富新闻/政府招标/国家统计局/DM查债通）
        try:
            from services.web_scraper import (
                search_eastmoney_news, search_gov_bid, fetch_stats_gov_data)
            for ent in _ents:
                name = ent["name"]
                parent_name = ent.get("parent", "")

                # 东方财富新闻
                for r in search_eastmoney_news(name, max_results=5):
                    _collect_source("eastmoney_news",
                        f'{r.get("title","")}\n{r.get("content","")}',
                        db, cls, name, "eastmoney_news",
                        title_override=r.get("title",""),
                        source_url=r.get("url",""))

                # 政府招标公告
                for r in search_gov_bid(parent_name or name, max_results=5):
                    _collect_source("gov_bid",
                        f'{r.get("title","")}\n{r.get("content","")}',
                        db, cls, name, "gov_bid",
                        title_override=r.get("title",""),
                        source_url=r.get("url",""))

            # 国家统计局（全局只查一次）
            for r in fetch_stats_gov_data():
                _collect_source("stats_gov",
                    f'{r.get("title","")}\n{r.get("content","")}',
                    db, cls, "宏观经济", "stats_gov",
                    title_override=r.get("title",""),
                    source_url=r.get("url",""))

            # DM 查债通
            try:
                from services.dm_client import search_dm
                for ent in _ents:
                    name = ent["name"]
                    for r in search_dm(name, cfg.dm_username, cfg.dm_password):
                        _collect_source("dm_zhai",
                            f'{r.get("title","")}\n{r.get("content","")}',
                            db, cls, name, "dm_zhai",
                            title_override=r.get("title",""),
                            source_url=r.get("url",""))
            except Exception as dm_e:
                logger.warning(f"[collector] DM client failed: {dm_e}")

        except Exception as e:
            logger.warning(f"[collector] Phase 3 scrapers failed: {e}")

        # Phase 4: 行业报告深层抓取
        try:
            from services.web_scraper import (search_deep_industry_reports,
                                              _summarize_report_with_llm)
            industries = list({e.get("industry", "") for e in _ents if e.get("industry")})
            ent_names = [e["name"] for e in _ents]
            for industry in industries[:5]:
                reports = search_deep_industry_reports(industry, ent_names, max_reports=2)
                for r in reports:
                    summary = _summarize_report_with_llm(
                        r["content"], ent_names, industry)
                    display = summary or r["content"][:300]
                    _collect_source("deep_report",
                        f'{r["title"]}\n\n{display}',
                        db, cls,
                        f"{industry}（行业报告）", "deep_report",
                        title_override=r.get("title",""),
                        source_url=r.get("url",""))
        except Exception as e:
            logger.warning(f"[collector] Deep industry reports failed: {e}")

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

        # 百度搜索 多维度采集（企业/行业/供应链/舆情）
        try:
            from services.web_search import _search_baidu

            _BAIDU_CALL_CAP = 200
            _baidu_calls = 0

            def _search_baidu_batch(queries, db, cls, ent_name, seen_queries,
                                     max_results=3):
                """批量百度搜索+采集。返回实际调用次数。"""
                nonlocal _baidu_calls
                batch_calls = 0
                for q in queries:
                    if q in seen_queries:
                        continue
                    if _baidu_calls >= _BAIDU_CALL_CAP:
                        logger.warning(
                            "Baidu search cap (%d) reached, skipping: %s",
                            _BAIDU_CALL_CAP, q)
                        break
                    seen_queries.add(q)
                    _baidu_calls += 1
                    batch_calls += 1
                    try:
                        for r in _search_baidu(q, max_results=max_results):
                            _collect_source("baidu_search",
                                f"{r.get('title','')}\n{r.get('content','')}",
                                db, cls, ent_name, "baidu_search",
                                title_override=r.get("title",""),
                                source_url=r.get("url",""))
                    except Exception:
                        logger.warning("Baidu query failed: %s", q)
                return batch_calls

            # 舆情 query 模板（Phase 1 — 新增）
            SENTIMENT_QUERIES = [
                "{name} 投诉 OR 曝光 OR 维权",
                "{name} 拖欠 OR 违约 OR 烂尾",
                "{name} 抖音 OR 微博",
                "{name} 负面 新闻",
                "{name} 事故 OR 安全",
                "{name} 维权 OR 讨薪",
                "{name} 监管 OR 处罚 OR 约谈",
                "{name} 破产 OR 重整",
            ]

            seen_queries = set()
            for ent in _ents:
                name = ent["name"]
                industry = ent.get("industry", "")
                role = ent.get("role", "乙方")
                parent = ent.get("parent", "")

                # 维度 1: 企业自身（风险/诉讼/经营）
                kw_list = ent.get("keywords", [name])
                queries_self = [
                    f"{kw} {suffix}"
                    for kw in kw_list[:2]
                    for suffix in ["风险 违约 诉讼", "经营 异常 处罚", "工商 变更 新闻"]
                ]
                _search_baidu_batch(queries_self, db, cls, name, seen_queries)

                # 维度 2: 行业（仅乙方触发）
                if role == "乙方" and industry:
                    queries_industry = [
                        f"{industry} {suffix}"
                        for suffix in ["行业 发展 规模 2026", "监管 政策 新规", "行业 风险 挑战"]
                    ]
                    _search_baidu_batch(queries_industry, db, cls, name, seen_queries)

                # 维度 3: 供应链（甲方自身+母公司）
                if role == "甲方":
                    queries_supply = [
                        f"{name} {suffix}"
                        for suffix in ["经营 风险 诉讼", "项目 动态 处罚", "财务 状况 新闻"]
                    ]
                    _search_baidu_batch(queries_supply, db, cls, name, seen_queries)
                    if parent:
                        _search_baidu_batch(
                            [f"{parent} 经营 风险 动态"], db, cls, name, seen_queries)

                # 维度 4: 舆情（新增 — Phase 1）
                queries_sentiment = [q.format(name=name) for q in SENTIMENT_QUERIES]
                _search_baidu_batch(queries_sentiment, db, cls, name, seen_queries)

        except Exception as e:
            logger.warning(f"[collector] Baidu multi-dimension search failed: {e}")

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
        seconds=int(_os.getenv("WARNING_CRON_INTERVAL", "7200")),
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
