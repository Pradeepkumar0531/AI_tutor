"""Typed application configuration loaded from environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # APP_ENV_FILE overrides the dotenv path (the test suite points it at the
    # null device so a developer's real backend/.env can never leak into or
    # break tests — tests must never touch live infrastructure).
    model_config = SettingsConfigDict(
        env_file=os.getenv("APP_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Learning Companion"
    app_env: Literal["local", "development", "staging", "production"] = "local"
    debug: bool = True
    api_prefix: str = "/api/v1"
    secret_key: str = "change-me-in-env"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    database_url: str = ""

    groq_api_key: str = ""
    google_api_key: str = ""

    # AI / knowledge pipeline. Model names and dimensions live ONLY here.
    # `models/gemini-embedding-001 (truncated to 768-d)` emits 768-dimensional vectors, matching the
    # fixed VECTOR(768) schema (see app/models/mixins.py: EMBEDDING_DIMENSIONS).
    google_embedding_model: str = "models/gemini-embedding-001"
    # Requested embedding width (Matryoshka truncation); must equal the
    # VECTOR(768) schema. 0 = model default (only for models natively 768-d).
    google_embedding_dimensions: int = 768
    embedding_dimensions: int = 768
    groq_model_concepts: str = "openai/gpt-oss-20b"
    groq_model_tutor: str = "openai/gpt-oss-20b"
    groq_model_quiz: str = "openai/gpt-oss-20b"
    # Finite client timeout for every Groq call (seconds): no request waits
    # forever on an external AI service.
    groq_timeout_seconds: int = 60
    quiz_default_question_count: int = 5
    quiz_max_question_count: int = 20
    quiz_max_generation_attempts: int = 2
    quiz_max_history: int = 50
    quiz_open_ended_max_answer_chars: int = 5000
    quiz_evaluation_max_tokens: int = 2048  # reasoning models burn tokens before answering
    quiz_max_retrieved_chunks: int = 4
    quiz_max_context_chars: int = 6000
    # Mastery engine (Prompt 9): deterministic EWMA-style updates. Scores are
    # stored 0-100 (existing Mastery.score semantics); the API presents 0-1.
    mastery_baseline: float = 0.5
    mastery_initial_confidence: float = 0.2
    mastery_recency_lambda: float = 0.02
    mastery_max_evidence_weight: float = 0.5
    mastery_trend_window: int = 5
    mastery_trend_threshold: float = 0.05
    tutor_max_history_messages: int = 20
    tutor_max_history_chars: int = 8000
    tutor_max_response_tokens: int = 4096  # reasoning models burn tokens before answering
    tutor_max_retrieved_chunks: int = 6
    tutor_max_context_chars: int = 8000
    tutor_max_concepts: int = 10
    tutor_max_retries: int = 1
    embedding_batch_size: int = 32
    embedding_timeout_seconds: int = 60
    embedding_max_retries: int = 3
    rag_top_k: int = 8
    rag_similarity_threshold: float = 0.3
    rag_max_context_chunks: int = 8
    rag_max_context_chars: int = 12000
    concept_max_input_chars: int = 12000
    concept_max_per_run: int = 20
    # Test-only seam: deterministic fake AI providers (embeddings + concepts).
    # Default off; enabled explicitly for unit tests without credentials and
    # the E2E worker. NEVER enable in production (see docs/TESTING.md).
    test_fake_ai: bool = False

    upstash_redis_url: str = ""
    upstash_redis_token: str = ""
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # Neon Object Storage (S3-compatible). The endpoint is explicit — copied
    # from the Neon console — never derived. Production selects
    # STORAGE_BACKEND=neon; missing values raise at wiring time.
    neon_storage_endpoint: str = ""
    neon_storage_region: str = ""
    neon_storage_access_key_id: str = ""
    neon_storage_secret_access_key: str = ""
    neon_storage_bucket_name: str = ""
    storage_backend: Literal["local", "neon"] = "local"
    local_storage_dir: str = "./storage"

    jwt_secret_key: str = "change-me-jwt"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # Minimal RBAC bootstrap: comma-separated emails promoted to admin on
    # register/login. No public role-setting endpoint exists by design.
    admin_emails: str = ""

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    # Login brute-force throttle: failed attempts per email per window before
    # 429. Generous enough to never trip on legitimate use or E2E (unique
    # emails per run); gateway-level IP limiting remains a deployment concern.
    login_max_attempts: int = 10
    login_attempt_window_seconds: int = 300
    # API docs (/docs, /openapi.json): on in dev, off in production unless
    # explicitly enabled — the schema must not be public by default.
    enable_api_docs: bool = False
    # SQLAlchemy pool (production-sensitive; local/dev defaults are modest).
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800

    # Materials: upload + async PDF processing (all values centrally defined here;
    # validation and the pipeline read them from Settings, never hardcoded).
    max_upload_bytes: int = 25 * 1024 * 1024
    processing_max_pages: int = 500
    processing_max_chars: int = 2_000_000
    processing_chunk_size: int = 1000
    processing_chunk_overlap: int = 150
    processing_min_chunk_chars: int = 100
    ocr_min_chars_per_page: int = 50
    ocr_enabled: bool = True
    # Embedded PDF image extraction. Thresholds filter decorative content
    # (logos, icons, bullets, tracking pixels): figures below 100px on either
    # side or under 2KB are almost never educational content, while the caps
    # bound worker memory/time (worst case ~50 images for a 25MB upload).
    pdf_image_extraction_enabled: bool = True
    pdf_min_image_width: int = 100
    pdf_min_image_height: int = 100
    pdf_min_image_bytes: int = 2048
    pdf_max_images_per_page: int = 10
    pdf_max_images_per_document: int = 50
    processing_stale_claim_minutes: int = 30
    # Filesystem broker root (dev/E2E stand-in when no Redis URL is configured).
    # Production uses Upstash Redis; nothing else changes.
    celery_filesystem_root: str = ""

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="before")
    @classmethod
    def _strip_all_str(cls, data: object) -> object:
        # Env/dotenv values often carry accidental surrounding whitespace
        # ("KEY= value"), which silently breaks URLs, keys, and endpoints.
        # Strip every incoming string once, at the boundary.
        if isinstance(data, dict):
            return {k: (v.strip() if isinstance(v, str) else v) for k, v in data.items()}
        return data

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _check_production_safety(self) -> Settings:
        # Deploying with dev-default CORS silently allows localhost origins
        # alongside real traffic patterns; production must be explicit.
        if self.is_production and "cors_origins" not in self.model_fields_set:
            raise ValueError(
                "CORS_ORIGINS must be set explicitly in production (dev defaults are not allowed)."
            )
        return self

    @model_validator(mode="after")
    def _check_embedding_dimensions(self) -> Settings:
        # Fail fast: the schema is fixed VECTOR(768); a model with any other
        # dimensionality must never silently truncate or pad vectors.
        from app.models.mixins import EMBEDDING_DIMENSIONS

        if self.embedding_dimensions != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"embedding_dimensions={self.embedding_dimensions} is incompatible "
                f"with the VECTOR({EMBEDDING_DIMENSIONS}) schema; refusing to start "
                "with a configuration that would corrupt vectors."
            )
        # Single source of truth: document and query embeddings share one
        # width. google_embedding_dimensions drives the provider's
        # output_dimensionality request while embedding_dimensions drives
        # validation/persistence — a mismatch would embed documents and
        # queries at different widths (silent retrieval failure).
        if self.google_embedding_dimensions != self.embedding_dimensions:
            raise ValueError(
                f"google_embedding_dimensions={self.google_embedding_dimensions} must equal "
                f"embedding_dimensions={self.embedding_dimensions}; refusing to start "
                "with a configuration that would split document/query widths."
            )
        return self

    @property
    def broker_url(self) -> str:
        if self.celery_broker_url:
            return self.celery_broker_url
        if self.upstash_redis_url:
            return self.upstash_redis_url
        return "redis://localhost:6379/0"

    @property
    def result_backend(self) -> str:
        if self.celery_result_backend:
            return self.celery_result_backend
        if self.upstash_redis_url:
            return self.upstash_redis_url
        return "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
