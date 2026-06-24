import os
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 加载 backend/.env（与 src 同级目录）；override=True 使 .env 覆盖系统里残留的旧 LLM_* 变量
_backend_root = Path(__file__).resolve().parent.parent
load_dotenv(_backend_root / ".env", override=True)
load_dotenv()


class SearchAPI(Enum):
    PERPLEXITY = "perplexity"
    TAVILY = "tavily"
    DUCKDUCKGO = "duckduckgo"
    SEARXNG = "searxng"
    ADVANCED = "advanced"
    LOCAL = "local"


class Configuration(BaseModel):
    """Configuration options for the deep research assistant."""

    max_web_research_loops: int = Field(
        default=3,
        title="Research Depth",
        description="Number of research iterations to perform",
    )
    local_llm: str = Field(
        default="llama3.2",
        title="Local Model Name",
        description="Name of the locally hosted LLM (Ollama/LMStudio)",
    )
    llm_provider: str = Field(
        default="ollama",
        title="LLM Provider",
        description="Provider identifier (ollama, lmstudio, or custom)",
    )
    search_api: SearchAPI = Field(
        default=SearchAPI.LOCAL,
        title="Search API",
        description="Web search API to use",
    )
    enable_notes: bool = Field(
        default=True,
        title="Enable Notes",
        description="Whether to store task progress in local notes",
    )
    notes_workspace: str = Field(
        default="./notes",
        title="Notes Workspace",
        description="Directory for Markdown notes persistence",
    )
    fetch_full_page: bool = Field(
        default=True,
        title="Fetch Full Page",
        description="Include the full page content in the search results",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        title="Ollama Base URL",
        description="Base URL for Ollama API (without /v1 suffix)",
    )
    lmstudio_base_url: str = Field(
        default="http://localhost:1234/v1",
        title="LMStudio Base URL",
        description="Base URL for LMStudio OpenAI-compatible API",
    )
    strip_thinking_tokens: bool = Field(
        default=True,
        title="Strip Thinking Tokens",
        description="Whether to strip <think> tokens from model responses",
    )
    use_tool_calling: bool = Field(
        default=False,
        title="Use Tool Calling",
        description="Use tool calling instead of JSON mode for structured output",
    )
    llm_api_key: Optional[str] = Field(
        default=None,
        title="LLM API Key",
        description="Optional API key when using custom OpenAI-compatible services",
    )
    llm_base_url: Optional[str] = Field(
        default=None,
        title="LLM Base URL",
        description="Optional base URL when using custom OpenAI-compatible services",
    )
    llm_model_id: Optional[str] = Field(
        default=None,
        title="LLM Model ID",
        description="Optional model identifier for custom OpenAI-compatible services",
    )
    llm_max_tokens: int = Field(
        default=8192,
        title="LLM max_tokens",
        description="Upper bound on completion tokens for OpenAI-compatible APIs",
    )
    llm_max_retries: int = Field(
        default=4,
        title="LLM transient retries",
        description="Retries on 5xx/429/timeout for invoke and stream",
    )
    llm_timeout: int = Field(
        default=120,
        title="LLM HTTP timeout seconds",
        description="OpenAI client timeout (per request)",
    )

    @classmethod
    def from_env(cls, overrides: Optional[dict[str, Any]] = None) -> "Configuration":
        """Create a configuration object using environment variables and overrides."""

        raw_values: dict[str, Any] = {}

        # Load values from environment variables based on field names
        for field_name in cls.model_fields.keys():
            env_key = field_name.upper()
            if env_key in os.environ:
                raw_values[field_name] = os.environ[env_key]

        # Additional mappings for explicit env names
        def _strip_env(key: str) -> Optional[str]:
            v = os.getenv(key)
            if v is None:
                return None
            s = v.strip()
            return s if s else None

        env_aliases = {
            "local_llm": _strip_env("LOCAL_LLM"),
            "llm_provider": _strip_env("LLM_PROVIDER"),
            "llm_api_key": _strip_env("LLM_API_KEY"),
            "llm_model_id": _strip_env("LLM_MODEL_ID"),
            "llm_base_url": _strip_env("LLM_BASE_URL"),
            "llm_max_tokens": os.getenv("LLM_MAX_TOKENS"),
            "llm_max_retries": os.getenv("LLM_MAX_RETRIES"),
            "llm_timeout": os.getenv("LLM_TIMEOUT"),
            "lmstudio_base_url": os.getenv("LMSTUDIO_BASE_URL"),
            "ollama_base_url": os.getenv("OLLAMA_BASE_URL"),
            "max_web_research_loops": os.getenv("MAX_WEB_RESEARCH_LOOPS"),
            "fetch_full_page": os.getenv("FETCH_FULL_PAGE"),
            "strip_thinking_tokens": os.getenv("STRIP_THINKING_TOKENS"),
            "use_tool_calling": os.getenv("USE_TOOL_CALLING"),
            "search_api": os.getenv("SEARCH_API"),
            "enable_notes": os.getenv("ENABLE_NOTES"),
            "notes_workspace": os.getenv("NOTES_WORKSPACE"),
        }

        for key, value in env_aliases.items():
            if value is not None:
                raw_values.setdefault(key, value)

        for k, v in list(raw_values.items()):
            if isinstance(v, str):
                raw_values[k] = v.strip()

        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    raw_values[key] = value

        cls._apply_llm_provider_defaults(raw_values)

        return cls(**raw_values)

    @staticmethod
    def _apply_llm_provider_defaults(raw_values: dict[str, Any]) -> None:
        """未显式设置 LLM_PROVIDER 时：若配置了远程 API，则走 OpenAI 兼容端点而非本地 Ollama。"""
        explicit = (os.getenv("LLM_PROVIDER") or "").strip().lower()
        if explicit:
            return
        base = raw_values.get("llm_base_url")
        key = raw_values.get("llm_api_key")
        if base and key:
            raw_values["llm_provider"] = "custom"

    def sanitized_ollama_url(self) -> str:
        """Ensure Ollama base URL includes the /v1 suffix required by OpenAI clients."""

        base = self.ollama_base_url.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        return base

    def resolved_model(self) -> Optional[str]:
        """Best-effort resolution of the model identifier to use."""

        return self.llm_model_id or self.local_llm


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
    warning_api_key: str = Field(default="", description="预警API认证Key")

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
            ths_username=os.getenv("THS_USERNAME", "dhsybl002"),
            ths_password=os.getenv("THS_PASSWORD", "5TSc27g4"),
            feishu_bot_token=os.getenv("FEISHU_BOT_TOKEN", ""),
            warning_api_key=os.getenv("WARNING_API_KEY", ""),
        )

