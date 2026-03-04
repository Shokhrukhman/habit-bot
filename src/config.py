from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    log_level: str = "INFO"
    admin_id: int = 6410377878


def load_settings() -> Settings:
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    admin_id_raw = os.getenv("ADMIN_ID", "6410377878").strip()

    if not bot_token:
        raise ValueError("BOT_TOKEN is not set in environment")
    if not database_url:
        raise ValueError("DATABASE_URL is not set in environment")
    try:
        admin_id = int(admin_id_raw)
    except ValueError as exc:
        raise ValueError("ADMIN_ID must be an integer telegram id") from exc

    return Settings(
        bot_token=bot_token,
        database_url=database_url,
        log_level=log_level,
        admin_id=admin_id,
    )
