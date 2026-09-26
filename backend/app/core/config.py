"""Centralized backend configuration (pydantic-settings).

All configuration is environment-driven; no secrets in source. Defaults are
safe for local development. Copy `.env.example` to `.env` to override.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# .env lives at the repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    # --- Application -------------------------------------------------------- #
    app_name: str = "Remedy-AI API"
    app_env: str = Field(default="development")  # development | test | production
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    log_level: str = "INFO"

    # --- Model serving ------------------------------------------------------ #
    # Which model generation the API serves. Phase 2 rule: reuse the Phase 1
    # modern predictor; do not retrain or alter ML behavior.
    model_version: str = "v2"
    models_dir: str = ""  # empty → ml.config default (models/v2)

    # --- Databases ---------------------------------------------------------- #
    # Default contains NO credentials: real values come from the gitignored
    # .env (see .env.example). Never put a real password in source code.
    database_url: str = "postgresql+psycopg://postgres:PLACEHOLDER@localhost:5432/remedy_ai"
    redis_url: str = "redis://localhost:6379/0"

    # --- CORS --------------------------------------------------------------- #
    # Comma-separated list. "*" is only ever honored for development; the
    # application refuses wildcard origins when app_env=production.
    cors_origins: str = "http://localhost:3000"

    # --- Authentication / sessions (Phase 6) --------------------------------- #
    # Argon2 password hashing (pwdlib). Parameters are the library defaults —
    # deliberately not tuned in source; raise OWASP work factors via env.
    # Session cookies: HttpOnly always; Secure only over HTTPS (production).
    # "__Host-" prefix requires Secure + Path=/ + no Domain, so it is enabled
    # only when the deployment is HTTPS with dedicated domains.
    session_ttl_seconds: int = 60 * 60 * 8  # 8h default, configurable
    session_cookie_name: str = "remedy_session"
    cookie_secure: bool = False  # env-driven; MUST be true in production
    cookie_domain: str = ""  # empty → host-only cookie
    use_host_prefixed_cookie: bool = False
    csrf_cookie_name: str = "remedy_csrf"
    csrf_header_name: str = "X-CSRF-Token"

    # --- Auth rate limiting (Redis fixed-window; conservative defaults) ------ #
    auth_rate_limit_register_per_hour: int = 10
    auth_rate_limit_login_per_hour: int = 20

    # --- Security headers (Phase 6) ------------------------------------------ #
    # HMAC signing secret for CSRF tokens. Empty in dev (a deterministic
    # fallback is derived from the DB URL); REQUIRED in production — the app
    # refuses to start with the fallback there. Never a real secret in source.
    secret_key: str = ""
    # HSTS is sent ONLY in production (the app must never instruct browsers
    # to force HTTPS on a local plain-HTTP dev server).
    hsts_max_age_seconds: int = 31536000

    @field_validator("session_ttl_seconds")
    @classmethod
    def _validate_session_ttl(cls, v: int) -> int:
        if not (60 <= v <= 60 * 60 * 24 * 7):
            raise ValueError("SESSION_TTL_SECONDS must be between 60 and 7 days")
        return v

    # --- RAG / knowledge base (Phase 4) -------------------------------------- #
    # Embedding provider: any OpenAI-compatible endpoint (OpenRouter, OpenAI,
    # Ollama, ...). Model + dimension are configuration: changing either
    # requires re-ingestion (the DB stores the model name per document).
    embedding_api_base: str = "https://openrouter.ai/api/v1"
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dimension: int = 1024
    embedding_timeout_seconds: float = 60.0
    rag_retrieval_top_k: int = 6
    rag_min_similarity: float = 0.25

    # --- LLM (Phase 4 guidance) ---------------------------------------------- #
    # OpenAI-compatible chat completions endpoint. Guidance is only generated
    # on explicit user request — never per page render.
    llm_api_base: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.2
    llm_timeout_seconds: float = 60.0
    llm_prompt_version: str = "v1"

    # --- Medical Report Ingestion (Phase 7) ---------------------------------- #
    storage_backend: str = "local"  # local | s3
    reports_storage_dir: str = "data/reports"
    reports_max_bytes: int = 10 * 1024 * 1024  # 10 MB default
    multimodal_model: str = ""  # if empty, falls back to llm_model
    reports_max_pdf_pages: int = 10

    # --- S3-compatible object storage (Phase 9) ------------------------------ #
    # Works with AWS S3, MinIO, Cloudflare R2, Backblaze B2, etc. Credentials
    # are environment-driven only; an empty access/secret pair means "use the
    # ambient IAM role / workload identity" (the recommended production setup).
    s3_endpoint_url: str = ""  # empty → real AWS S3
    s3_region: str = "us-east-1"
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_use_ssl: bool = True
    s3_addressing_style: str = "path"  # path | virtual
    s3_server_side_encryption: str = ""  # e.g. "AES256" or "aws:kms"
    s3_kms_key_id: str = ""
    s3_presigned_expiry_seconds: int = 900
    s3_connect_timeout_seconds: float = 10.0
    s3_read_timeout_seconds: float = 30.0

    # --- OpenTelemetry (Phase 9) ---------------------------------------------- #
    # When disabled (the default) spans are created but not exported. The
    # endpoint is an OTLP/HTTP base URL; only operational attributes are ever
    # recorded (see backend/app/telemetry.py for the allowlist).
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = ""

    @field_validator("storage_backend")
    @classmethod
    def _validate_storage_backend(cls, v: str) -> str:
        allowed = {"local", "s3"}
        normalized = v.strip().lower()
        if normalized not in allowed:
            raise ValueError(
                f"STORAGE_BACKEND must be one of {sorted(allowed)}, got '{v}'"
            )
        return normalized


    @field_validator("cors_origins")
    @classmethod
    def _split_origins(cls, v: str) -> list[str]:
        return [o.strip() for o in v.split(",") if o.strip()]

    @field_validator("app_env", "log_level")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return v.strip().lower()

    model_config = {
        "env_file": str(ENV_FILE),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def csrf_secret_configured(self) -> bool:
        return bool(self.secret_key) or not self.is_production

    @property
    def session_cookie_name_resolved(self) -> str:
        """__Host- prefix (Secure, Path=/, no Domain) when topology allows."""
        if self.use_host_prefixed_cookie:
            if not (self.cookie_secure and not self.cookie_domain):
                raise ValueError(
                    "__Host- cookie requires COOKIE_SECURE=true and no COOKIE_DOMAIN"
                )
            return f"__Host-{self.session_cookie_name}"
        return self.session_cookie_name

    @property
    def rag_configured(self) -> bool:
        """True when an embedding provider is configured."""
        return bool(self.embedding_api_key and self.embedding_model)

    @property
    def llm_configured(self) -> bool:
        """True when an LLM provider is configured."""
        return bool(self.llm_api_key and self.llm_model)

    @property
    def cors_origin_list(self) -> list[str]:
        if self.is_production and "*" in self.cors_origins:
            raise ValueError(
                "CORS wildcard origin '*' is not allowed in production; "
                "configure explicit origins via CORS_ORIGINS."
            )
        return self.cors_origins

    @property
    def s3_configured(self) -> bool:
        """True when an S3 bucket is set (endpoint and credentials optional)."""
        return bool(self.s3_bucket)

    def validate_production(self) -> None:
        """Fail fast on insecure production configuration (Phase 9).

        Called from the app factory when APP_ENV=production. Each rule here
        corresponds to a real vulnerability class, and the messages name the
        exact environment variable to set.
        """
        if not self.is_production:
            return

        problems: list[str] = []

        # 1. Secret material must be explicitly provided (no dev fallback).
        if not self.secret_key:
            problems.append(
                "SECRET_KEY is required in production (signing/CSRF secret)."
            )
        elif len(self.secret_key) < 32:
            problems.append(
                "SECRET_KEY must be at least 32 characters of high-entropy "
                "material in production."
            )

        # 2. Cookies must only travel over TLS.
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true in production.")

        # 3. CORS must be an explicit allowlist. `cors_origins` is a list by the
        #    time it reaches here (see the _split_origins validator).
        if "*" in self.cors_origins or not self.cors_origins:
            problems.append(
                "CORS_ORIGINS must list explicit origins in production "
                "(wildcards are refused)."
            )

        # 4. Session lifetime must be bounded.
        if self.session_ttl_seconds > 60 * 60 * 24:
            problems.append("SESSION_TTL_SECONDS must not exceed 24 hours.")

        # 5. Debug-level logging would risk leaking request detail.
        if self.log_level.upper() == "DEBUG":
            problems.append("LOG_LEVEL=DEBUG is not allowed in production.")

        # 6. Object storage must be explicitly configured when selected.
        if self.storage_backend == "s3" and not self.s3_bucket:
            problems.append(
                "S3_BUCKET is required when STORAGE_BACKEND=s3."
            )

        if problems:
            raise RuntimeError(
                "Insecure production configuration:\n  - "
                + "\n  - ".join(problems)
            )

    def validate_runtime_services(self) -> list[str]:
        """Non-fatal capability report for startup logging and /ready.

        Returns a list of human-readable warnings. Never includes values of
        secrets — only whether each integration is configured.
        """
        warnings: list[str] = []
        if not self.llm_configured:
            warnings.append(
                "LLM provider not configured: AI guidance is unavailable."
            )
        if not self.rag_configured:
            warnings.append(
                "Embedding provider not configured: RAG retrieval is unavailable."
            )
        if self.storage_backend == "s3" and not self.s3_configured:
            warnings.append("STORAGE_BACKEND=s3 but S3_BUCKET is not set.")
        if self.storage_backend == "local" and self.is_production:
            warnings.append(
                "STORAGE_BACKEND=local in production: uploaded reports land on "
                "container-local disk and are lost on redeploy. Use s3 for "
                "multi-instance deployments."
            )
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()
