from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    nvidia_nim_api_key: str = ""
    anthropic_api_key: str = ""
    ncbi_api_key: str = ""
    supabase_url: str = ""
    supabase_service_key: str = ""
    frontend_url: str = "http://localhost:3000"

    model_config = {"env_file": [".env", "../.env"], "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
