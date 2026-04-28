import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # LLM provider: "gemini" (default) or "groq" (free, for dev/testing)
    GENESIS_LLM_PROVIDER: str = os.getenv("GENESIS_LLM_PROVIDER", "gemini")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # Dreaming: set GENESIS_DREAMING=0 to disable idle dream cycles entirely
    GENESIS_DREAMING: bool = os.getenv("GENESIS_DREAMING", "1") not in ("0", "false", "no")
    GENESIS_IDLE_DREAM_AFTER_S: int = int(os.getenv("GENESIS_IDLE_DREAM_AFTER_S", "3600"))

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./genesis.db")


settings = Settings()
