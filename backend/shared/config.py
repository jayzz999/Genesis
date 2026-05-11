import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()


def _bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() not in ("0", "false", "no", "off", "")


def _csv_env(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _render_external_url() -> str:
    explicit = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    service_name = os.getenv("RENDER_SERVICE_NAME", "").strip()
    if service_name:
        return f"https://{service_name}.onrender.com"
    return ""


def _render_host() -> str:
    url = _render_external_url()
    if not url:
        return ""
    return urlparse(url).netloc or url.replace("https://", "").replace("http://", "").split("/", 1)[0]


def _default_cors_origins() -> str:
    if os.getenv("GENESIS_ENV", "development").lower() == "production":
        return _render_external_url()
    return "*"


def _default_trusted_hosts() -> str:
    if os.getenv("GENESIS_ENV", "development").lower() == "production":
        return _render_host()
    return "*"


def _production_safe_csv_env(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    if os.getenv("GENESIS_ENV", "development").lower() == "production" and value.strip() == "*":
        if name == "GENESIS_CORS_ORIGINS" and _render_external_url():
            value = _render_external_url()
        elif name == "GENESIS_TRUSTED_HOSTS" and _render_host():
            value = _render_host()
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    GENESIS_ENV: str = os.getenv("GENESIS_ENV", "development").lower()
    GENESIS_API_TOKEN: str = os.getenv("GENESIS_API_TOKEN", "")
    GENESIS_REQUIRE_API_TOKEN: bool = _bool_env("GENESIS_REQUIRE_API_TOKEN", "0")
    GENESIS_CORS_ORIGINS: list[str] = _production_safe_csv_env("GENESIS_CORS_ORIGINS", _default_cors_origins())
    GENESIS_TRUSTED_HOSTS: list[str] = _production_safe_csv_env("GENESIS_TRUSTED_HOSTS", _default_trusted_hosts())

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # LLM provider: "gemini" (default), "groq", or "mock" for no-key local demos/tests.
    GENESIS_LLM_PROVIDER: str = os.getenv("GENESIS_LLM_PROVIDER", "gemini")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # Dreaming: set GENESIS_DREAMING=0 to disable idle dream cycles entirely
    GENESIS_DREAMING: bool = os.getenv("GENESIS_DREAMING", "1") not in ("0", "false", "no")
    GENESIS_IDLE_DREAM_AFTER_S: int = int(os.getenv("GENESIS_IDLE_DREAM_AFTER_S", "3600"))

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./genesis.db")
    GENESIS_RELOAD: bool = _bool_env("GENESIS_RELOAD", "1")
    GENESIS_RELOAD_DIRS: list[str] = _csv_env("GENESIS_RELOAD_DIRS", "backend")
    GENESIS_RELOAD_EXCLUDES: list[str] = _csv_env(
        "GENESIS_RELOAD_EXCLUDES",
        "organisms,approvals,memories,tool_runs,collaborations,mcp_servers,frontend/dist,node_modules,.git,__pycache__,*.db,*.sqlite,*.sqlite3",
    )

    @property
    def is_production(self) -> bool:
        return self.GENESIS_ENV == "production"

    def validate_startup(self) -> None:
        errors = []
        if self.is_production:
            if self.GENESIS_LLM_PROVIDER == "mock":
                errors.append("GENESIS_LLM_PROVIDER=mock is not allowed when GENESIS_ENV=production")
            if not self.GENESIS_REQUIRE_API_TOKEN:
                errors.append("GENESIS_REQUIRE_API_TOKEN=1 is required when GENESIS_ENV=production")
            if not self.GENESIS_API_TOKEN or len(self.GENESIS_API_TOKEN) < 24:
                errors.append("GENESIS_API_TOKEN must be set to at least 24 characters in production")
            if "*" in self.GENESIS_CORS_ORIGINS:
                errors.append("GENESIS_CORS_ORIGINS must not include '*' in production")
            if "*" in self.GENESIS_TRUSTED_HOSTS:
                errors.append("GENESIS_TRUSTED_HOSTS must not include '*' in production")
        if self.GENESIS_LLM_PROVIDER == "gemini" and not self.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY is required when GENESIS_LLM_PROVIDER=gemini")
        if self.GENESIS_LLM_PROVIDER == "groq" and not self.GROQ_API_KEY:
            errors.append("GROQ_API_KEY is required when GENESIS_LLM_PROVIDER=groq")
        if errors:
            raise RuntimeError("Invalid Genesis configuration: " + "; ".join(errors))


settings = Settings()
