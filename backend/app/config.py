from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_url: str = "http://192.168.1.233:11434/api/chat"
    ollama_model: str = "llama3.1:8b"
    port: int = 8765
    heartbeat_timeout_sec: float = 15.0
    max_saves: int = 5


settings = Settings()
