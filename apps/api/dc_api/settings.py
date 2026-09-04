"""Application settings (12-factor, env-driven)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # -- database ----------------------------------------------------------
    # Postgres in docker-compose; a file-backed SQLite works for local dev.
    database_url: str = "sqlite:///./storage/foreman.db"

    # -- storage -----------------------------------------------------------
    # "local" keeps files under storage_dir; "s3" talks to MinIO/S3.
    storage_backend: str = "local"
    storage_dir: str = "./storage/files"
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "foreman"

    # -- background jobs ---------------------------------------------------
    # "inline" runs the analysis in a thread (dev); "celery" uses Redis.
    job_backend: str = "inline"
    redis_url: str = "redis://localhost:6379/0"

    # -- vision model ------------------------------------------------------
    # Any OpenAI-compatible VLM endpoint (vLLM / Ollama / LM Studio).
    # Leave vlm_base_url empty to run deterministic extraction only.
    vlm_base_url: str | None = None
    vlm_model: str = "qwen3-vl-8b-instruct"
    vlm_api_key: str = "not-needed"
    vlm_timeout: float = 300.0
    vlm_max_tokens: int = 4096
    # Extra JSON merged into each chat request (e.g. Ollama's {"think": false}).
    vlm_extra_json: str = '{"think": false}'
    prompt_version: str = "v1"
    prompts_dir: str = "./prompts"

    # -- OCR ---------------------------------------------------------------
    # auto | paddle | tesseract | none
    ocr_provider: str = "auto"
    ocr_render_dpi: int = 300

    # -- CAD (DWG/DXF) -----------------------------------------------------
    # DWG needs the free ODA File Converter; DXF works out of the box.
    oda_converter_path: str | None = None

    # -- misc --------------------------------------------------------------
    page_render_dpi: int = 200
    max_upload_mb: int = 100
    cors_origins: str = "http://localhost:3000"

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
