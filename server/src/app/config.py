"""App configuration. Everything lives under one data dir by default; media roots
are configured in the database (media_root table), not here."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IMMERSION_", env_file=".env", extra="ignore")

    data_dir: Path = Path.home() / ".local/share/immersion"
    # bundled reference data (cedict.txt, hsk30.json); repo layout by default
    ref_dir: Path = Path(__file__).resolve().parents[3] / "data"
    host: str = "127.0.0.1"
    port: int = 8770
    # AnkiConnect
    anki_url: str = "http://127.0.0.1:8765"
    # worker
    poll_interval: float = 2.0
    # AI provider (claude CLI); translation batches stay small + literal
    ai_model: str = "claude-haiku-4-5"
    # edge-tts voice for exported word audio
    tts_voice: str = "zh-CN-XiaoxiaoNeural"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "immersion.db"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def thumb_dir(self) -> Path:
        return self.cache_dir / "thumbs"

    @property
    def audio_dir(self) -> Path:
        """Ingest-transcoded podcast m4a; served at /media/audio/{item_id}.m4a."""
        return self.cache_dir / "audio"

    @property
    def whisper_dir(self) -> Path:
        return self.cache_dir / "whisper"


settings = Settings()
