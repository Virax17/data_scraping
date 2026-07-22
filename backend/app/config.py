"""Static config: secrets from env (.env), tunable defaults from settings.yaml.
Live/tunable values are stored in Mongo (AppSettings) and edited via the API;
settings.yaml is only the first-boot seed."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

APP_DIR = Path(__file__).parent
PROJECT_ROOT = APP_DIR.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Config(BaseModel):
    apollo_api_key: str = ""
    lusha_api_key: str = ""
    anthropic_api_key: str = ""
    cerebras_api_key: str = ""
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "tritorc_enrich"
    jwt_secret: str = "change-me"
    output_dir: str = str(PROJECT_ROOT / "outputs")
    worker_concurrency: int = 3


@lru_cache(maxsize=1)
def get_config() -> Config:
    return Config(
        apollo_api_key=os.getenv("APOLLO_API_KEY", ""),
        lusha_api_key=os.getenv("LUSHA_API_KEY", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        cerebras_api_key=os.getenv("CEREBRAS_API_KEY", ""),
        mongo_uri=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        mongo_db=os.getenv("MONGO_DB", "tritorc_enrich"),
        jwt_secret=os.getenv("JWT_SECRET", "change-me"),
        output_dir=os.getenv("OUTPUT_DIR", str(PROJECT_ROOT / "outputs")),
        worker_concurrency=int(os.getenv("WORKER_CONCURRENCY", "3")),
    )


@lru_cache(maxsize=1)
def default_settings() -> dict:
    with open(APP_DIR / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def get_live_settings() -> dict:
    """Merged view: yaml defaults overlaid with the Mongo settings doc."""
    from app.models.misc import AppSettings

    merged = dict(default_settings())
    doc = await AppSettings.find_one(AppSettings.key == "app")
    if doc:
        merged.update(doc.values)
    return merged
