from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _load_dotenv(path: Path) -> None:
    """Load simple local KEY=VALUE entries without overriding shell-provided values."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not _ENV_KEY.match(key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    storage_dir: Path
    max_upload_bytes: int = 25 * 1024 * 1024
    web_search_enabled: bool = True
    demo_mode: bool = True
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    api_key: str | None = None
    allowed_origins: tuple[str, ...] = ()
    web_search_provider: str = "duckduckgo_html"
    web_search_api_url: str | None = None
    web_search_api_key: str | None = None
    tavily_api_key: str | None = None
    llm_provider: str = "deterministic"
    llm_api_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = ""
    enterprise_kb_dir: Path | None = None
    pinecone_api_key: str | None = None
    pinecone_index_host: str | None = None
    pinecone_namespace: str = "__default__"
    pinecone_api_version: str = "2026-04"
    pinecone_mode: str = "vectors"
    pinecone_text_field: str = "chunk_text"
    ocr_enabled: bool = True

    @property
    def upload_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def artifact_dir(self) -> Path:
        return self.storage_dir / "artifacts"

    @property
    def run_dir(self) -> Path:
        return self.storage_dir / "runs"

    @property
    def registry_path(self) -> Path:
        return self.storage_dir / "registry.json"

    def ensure_directories(self) -> None:
        for path in (self.storage_dir, self.upload_dir, self.artifact_dir, self.run_dir):
            path.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    _load_dotenv(ROOT_DIR / ".env")
    storage_value = os.getenv("APP_STORAGE_DIR")
    storage_dir = Path(storage_value).expanduser() if storage_value else ROOT_DIR / "storage"
    host = os.getenv("APP_HOST", "127.0.0.1")
    # Managed hosts (Render, Heroku, Cloud Run) inject the bound port as PORT.
    port = int(os.getenv("APP_PORT") or os.getenv("PORT") or "8000")
    configured_origins = tuple(item.strip() for item in os.getenv("ALLOWED_ORIGINS", "").split(",") if item.strip())
    enterprise_kb_value = os.getenv("ENTERPRISE_KB_DIR")
    enterprise_kb_dir = Path(enterprise_kb_value).expanduser() if enterprise_kb_value else ROOT_DIR / "samples" / "input"
    return Settings(
        root_dir=ROOT_DIR,
        storage_dir=storage_dir,
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024))),
        web_search_enabled=os.getenv("WEB_SEARCH_ENABLED", "true").lower() not in {"0", "false", "no"},
        demo_mode=os.getenv("DEMO_MODE", "true").lower() not in {"0", "false", "no"},
        app_host=host,
        app_port=port,
        api_key=os.getenv("API_KEY") or None,
        allowed_origins=configured_origins or (f"http://{host}:{port}", f"http://localhost:{port}"),
        web_search_provider=os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo_html"),
        web_search_api_url=os.getenv("WEB_SEARCH_API_URL") or None,
        web_search_api_key=os.getenv("WEB_SEARCH_API_KEY") or None,
        tavily_api_key=os.getenv("TAVILY_API_KEY") or None,
        llm_provider=os.getenv("LLM_PROVIDER", "deterministic"),
        llm_api_url=os.getenv("LLM_API_URL") or None,
        llm_api_key=os.getenv("LLM_API_KEY") or None,
        llm_model=os.getenv("LLM_MODEL", ""),
        enterprise_kb_dir=enterprise_kb_dir,
        pinecone_api_key=os.getenv("PINECONE_API_KEY") or None,
        pinecone_index_host=os.getenv("PINECONE_INDEX_HOST") or None,
        pinecone_namespace=os.getenv("PINECONE_NAMESPACE", "__default__"),
        pinecone_api_version=os.getenv("PINECONE_API_VERSION", "2026-04"),
        pinecone_mode=os.getenv("PINECONE_MODE", "vectors"),
        pinecone_text_field=os.getenv("PINECONE_TEXT_FIELD", "chunk_text"),
        ocr_enabled=os.getenv("OCR_ENABLED", "true").lower() not in {"0", "false", "no"},
    )
