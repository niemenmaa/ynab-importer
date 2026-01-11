import json
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    ynab_api_token: str = ""
    budget_id: str = ""
    database_url: str = "sqlite+aiosqlite:///./ynab_importer.db"
    
    class Config:
        env_file = ".env"


def load_config_from_json() -> dict:
    """Load configuration from config.json file."""
    config_path = Path(__file__).parent.parent / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance, merging JSON config with environment."""
    json_config = load_config_from_json()
    return Settings(**json_config)
