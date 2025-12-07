import yaml
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
import os

# Load .env from project root
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)


class ProcessingSettings(BaseSettings):
    workers: int = 10
    batch_size: int = 100
    max_retries: int = 3
    timeout: int = 300


class StorageSettings(BaseSettings):
    type: str = "local"
    bucket: str = "lab-reports"
    base_path: str = "storage"


class DatabaseSettings(BaseSettings):
    url: str = "sqlite:///./lab_extraction.db"


class GeminiSettings(BaseSettings):
    model: str = ""
    rate_limit: int = 3
    api_key: str | None = None


class RedisSettings(BaseSettings):
    url: str = "redis://localhost:6379/0"


class StandardizationSettings(BaseSettings):
    """Settings for test name standardization."""
    fuzzy_threshold: float = 0.85  # Minimum confidence for fuzzy matching
    llm_fallback: bool = True      # Whether to use LLM for unknown tests


class Settings(BaseSettings):
    processing: ProcessingSettings = ProcessingSettings()
    storage: StorageSettings = StorageSettings()
    database: DatabaseSettings = DatabaseSettings()
    gemini: GeminiSettings = GeminiSettings()
    redis: RedisSettings = RedisSettings()
    standardization: StandardizationSettings = StandardizationSettings()

    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"


@lru_cache()
def get_settings() -> Settings:
    """Load settings from YAML config file and environment variables."""
    config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    
    yaml_config = {}
    if config_path.exists():
        with open(config_path) as f:
            yaml_config = yaml.safe_load(f) or {}
    
    # Environment variables take precedence
    return Settings(**yaml_config)
