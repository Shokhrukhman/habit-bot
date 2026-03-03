from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    log_level: str = "INFO"


def load_settings() -> Settings:
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()

    if not bot_token:
        raise ValueError("BOT_TOKEN is not set in environment")
    if not database_url:
        raise ValueError("DATABASE_URL is not set in environment")

    return Settings(
        bot_token=bot_token,
        database_url=database_url,
        log_level=log_level,
    )
