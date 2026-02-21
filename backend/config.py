from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    nvidia_nim_api_key: str = ""
    anthropic_api_key: str = ""
    ncbi_api_key: str = ""

    model_config = {"env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
