from functools import lru_cache
from pathlib import Path
from typing import Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    APP_NAME: str = Field(...)
    DEBUG: bool = Field(...)

    DATABASE_URL: str = Field(...)
    # Optional dedicated Postgres schema to isolate this app's tables from
    # anything else living in the same database (e.g. a shared Supabase project).
    # Leave empty for SQLite or to use the default `public` schema.
    DB_SCHEMA: str | None = Field(default=None)
    # Serverless (Vercel/Lambda): use NullPool so each invocation doesn't hold a
    # connection — pair with the Supabase pooler (:6543). Off for container/VM.
    DB_USE_NULLPOOL: bool = Field(default=False)
    # Run create_all / schema-evolve / seed on startup. Disable on serverless
    # (run it once out-of-band) so cold starts stay fast and don't hammer the DB.
    RUN_STARTUP_INIT: bool = Field(default=True)
    CORS_ORIGINS: list[str] = Field(...)
    # Public base URL of the frontend (used in emails: sign-in links + hosted
    # logo). Defaults to the deployed app; override in .env for other envs.
    # No trailing slash. (Avoid localhost here — it leaks into supplier emails.)
    APP_BASE_URL: str = Field(default="https://supplier-followup-module-atj8.vercel.app")

    JWT_SECRET: str = Field(...)
    JWT_ALGORITHM: str = Field(...)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(...)

    # Default admin bootstrapped on first startup (idempotent).
    SEED_ADMIN_EMAIL: str = Field(default="admin@example.com")
    SEED_ADMIN_PASSWORD: str = Field(default="ChangeMe!123")
    SEED_ADMIN_NAME: str = Field(default="System Admin")

    # Shared secret required to call the /api/webhooks/* endpoints (machine-to-
    # machine). When empty, the webhook endpoints reject all calls (fail closed).
    WEBHOOK_SECRET: str | None = Field(default=None)

    # ── LLM / AI (OpenAI-compatible endpoint, e.g. NVIDIA NIM) ────────────────
    LLM_ENABLED: bool = Field(default=False)
    LLM_BASE_URL: str = Field(default="https://integrate.api.nvidia.com/v1")
    LLM_API_KEY: str | None = Field(default=None)
    LLM_MODEL: str = Field(default="meta/llama-3.3-70b-instruct")
    LLM_MAX_TOKENS: int = Field(default=1024)
    LLM_TEMPERATURE: float = Field(default=0.7)
    # gpt-oss-only reasoning effort (low/medium/high). Leave EMPTY for llama/other
    # models — passing it to them can be rejected.
    LLM_REASONING_EFFORT: str = Field(default="")
    # Hard request timeout (seconds) so a slow/hung LLM can't block the UI.
    # Fail fast and fall back to the deterministic template on timeout.
    LLM_TIMEOUT_SECONDS: float = Field(default=30.0)
    # Agentic chat makes several sequential tool-calling round-trips and has no
    # template fallback, so it gets a longer per-request budget than the fail-
    # fast helpers above (free-tier 70B tool-calling can take ~30-40s per call).
    LLM_AGENT_TIMEOUT_SECONDS: float = Field(default=60.0)

    # ── Agentic assistant + AI feature toggles ───────────────────────────────
    # Let the Assistant chatbot call DB tools (PO lookups, supplier search, RAG).
    AI_AGENT_ENABLED: bool = Field(default=True)
    # Max tool-call rounds before the agent is forced to answer.
    AI_AGENT_MAX_ROUNDS: int = Field(default=4)
    # Auto-classify (category/urgency/action) incoming customer mails on fetch.
    AI_TRIAGE_ENABLED: bool = Field(default=False)
    # AI-polish RED/BLACK PO follow-up bodies (falls back to template on error).
    AI_PO_FOLLOWUP_ENABLED: bool = Field(default=False)

    # ── RAG / vector memory (pgvector on Postgres; no-op on SQLite) ───────────
    # Master switch. When false the agent runs SQL-only and indexing is skipped.
    RAG_ENABLED: bool = Field(default=False)
    # Embedding endpoint (OpenAI-compatible). Defaults reuse the NVIDIA NIM key.
    EMBED_BASE_URL: str = Field(default="https://integrate.api.nvidia.com/v1")
    EMBED_API_KEY: str | None = Field(default=None)  # falls back to LLM_API_KEY
    EMBED_MODEL: str = Field(default="nvidia/nv-embedqa-e5-v5")
    EMBED_DIM: int = Field(default=1024)
    # NVIDIA embedqa models require an input_type ("passage" for docs, "query"
    # for searches). Harmless for providers that ignore it.
    EMBED_USES_INPUT_TYPE: bool = Field(default=True)
    EMBED_TIMEOUT_SECONDS: float = Field(default=30.0)
    # How many top chunks the search_knowledge tool / draft retrieval pulls.
    RAG_TOP_K: int = Field(default=5)

    RED_AI_AFTER_DAYS: int = Field(...)

    # ── Mail automation toggles (safe defaults: everything OFF) ───────────
    SCHEDULER_ENABLED: bool = Field(...)
    MAIL_INBOX_ENABLED: bool = Field(...)
    SMTP_ENABLED: bool = Field(...)
    AUTO_PO_FOLLOWUP_ENABLED: bool = Field(default=False)
    MAIL_FETCH_PROTOCOL: str = Field(...)
    MAIL_INBOX_USE_SSL: bool = Field(...)

    # Inbound mailbox credentials (used for IMAP or POP3 mode)
    IMAP_HOST: str = Field(...)
    IMAP_PORT: int = Field(...)
    IMAP_USER: str = Field(...)
    IMAP_PASSWORD: str = Field(...)
    IMAP_FOLDER: str = Field(...)

    # SMTP (outgoing)
    SMTP_HOST: str = Field(...)
    SMTP_PORT: int = Field(...)
    SMTP_USER: str = Field(...)
    SMTP_PASSWORD: str = Field(...)
    SMTP_FROM: str = Field(...)

    # Cron intervals (minutes)
    MAIL_FETCH_INTERVAL_MINUTES: int = Field(...)
    STATUS_CHANGE_INTERVAL_MINUTES: int = Field(...)
    AUTO_REPLY_INTERVAL_MINUTES: int = Field(...)
    MAIL_SEND_INTERVAL_MINUTES: int = Field(...)

    # Outbound send throughput: how many parallel SMTP connections the send
    # worker uses, and the max messages drained per run. Safe defaults; override
    # in .env for heavier traffic.
    SMTP_SEND_WORKERS: int = Field(default=4)
    MAIL_SEND_BATCH_LIMIT: int = Field(default=50)

    @property
    def embed_api_key(self) -> str | None:
        """Embedding key, falling back to the chat LLM key (same NVIDIA account)."""
        return self.EMBED_API_KEY or self.LLM_API_KEY

    @field_validator("DB_SCHEMA", mode="before")
    @classmethod
    def validate_db_schema(cls, value: Any) -> Any:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        import re
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", text):
            raise ValueError("DB_SCHEMA must be a simple identifier (letters, digits, underscore)")
        return text

    @field_validator("MAIL_FETCH_PROTOCOL", mode="before")
    @classmethod
    def parse_mail_fetch_protocol(cls, value: Any) -> Any:
        normalized = str(value).strip().upper()
        if normalized not in {"IMAP", "POP3"}:
            raise ValueError("MAIL_FETCH_PROTOCOL must be IMAP or POP3")
        return normalized

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no", "off"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "yes", "on"}:
                return True
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
