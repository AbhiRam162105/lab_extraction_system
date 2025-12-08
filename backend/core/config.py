import yaml
import re
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


def substitute_env_vars(value):
    """
    Recursively substitute ${VAR_NAME} or ${VAR_NAME:-default} patterns 
    with environment variable values.
    """
    if isinstance(value, str):
        # Pattern matches ${VAR_NAME} or ${VAR_NAME:-default_value}
        pattern = r'\$\{([^}:]+)(?::-([^}]*))?\}'
        
        def replace_match(match):
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else ""
            return os.environ.get(var_name, default_value)
        
        return re.sub(pattern, replace_match, value)
    elif isinstance(value, dict):
        return {k: substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [substitute_env_vars(item) for item in value]
    return value


def load_yaml_with_env(yaml_path: Path) -> dict:
    """Load YAML file with environment variable substitution."""
    if not yaml_path.exists():
        return {}
    
    with open(yaml_path) as f:
        raw_config = yaml.safe_load(f) or {}
    
    return substitute_env_vars(raw_config)


class ProcessingSettings(BaseSettings):
    workers: int = 10
    batch_size: int = 15
    max_retries: int = 3
    timeout: int = 300
    max_concurrent_workers: int = 32
    enable_caching: bool = True
    cache_ttl_hours: int = 24


class StorageSettings(BaseSettings):
    type: str = "local"
    bucket: str = "lab-reports"
    base_path: str = "storage"


class DatabaseSettings(BaseSettings):
    url: str = "sqlite:///./lab_extraction.db"


class GeminiSettings(BaseSettings):
    model: str = ""
    rate_limit: int = 10
    api_key: str | None = None


class RedisSettings(BaseSettings):
    url: str = "redis://localhost:6379/0"


class StandardizationSettings(BaseSettings):
    """Settings for test name standardization."""
    fuzzy_threshold: float = 0.85
    llm_fallback: bool = True


class RateLimitingSettings(BaseSettings):
    """Settings for API rate limiting."""
    requests_per_minute: int = 15
    adaptive_backoff: bool = True
    backoff_factor: float = 0.8
    recovery_threshold: int = 10


class PreprocessingSettings(BaseSettings):
    """Settings for image preprocessing."""
    parallel_workers: int = 8
    quality_threshold: int = 100
    max_dimension: int = 2048
    jpeg_quality: int = 85


class Settings(BaseSettings):
    processing: ProcessingSettings = ProcessingSettings()
    storage: StorageSettings = StorageSettings()
    database: DatabaseSettings = DatabaseSettings()
    gemini: GeminiSettings = GeminiSettings()
    redis: RedisSettings = RedisSettings()
    standardization: StandardizationSettings = StandardizationSettings()
    rate_limiting: RateLimitingSettings = RateLimitingSettings()
    preprocessing: PreprocessingSettings = PreprocessingSettings()

    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"
        extra = "ignore"  # Ignore extra fields not in the model


@lru_cache()
def get_settings() -> Settings:
    """Load settings from YAML config file with environment variable substitution."""
    config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    
    # Load YAML with ${VAR_NAME} substitution from .env
    yaml_config = load_yaml_with_env(config_path)
    
    # Environment variables take precedence via pydantic-settings
    return Settings(**yaml_config)
