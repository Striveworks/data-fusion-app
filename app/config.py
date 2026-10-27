from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    postgres_url: str = "postgresql+psycopg://fusion:fusion@localhost:5432/fusion"
    timescale_url: str = "postgresql+psycopg://fusion:fusion@localhost:5433/fusion"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minio"
    minio_secret_key: str = "minio-secret"
    minio_bucket: str = "fusion"
    minio_secure: bool = False
    chariot_credentials_file: str = "data-fusion-app.json"
    chariot_detection_model_id: str = ""
    chariot_vlm_model_id: str = ""
    chariot_workflow_id: str = ""
    chariot_fusion_agent: str = "Data Fusion Orchestrator"
    chariot_project_id: str = ""
    mcp_public_url: str = "http://localhost:8000/mcp"
    worker_poll_seconds: float = 1.0
    fusion_timeout_seconds: int = 300

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
