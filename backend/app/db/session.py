from __future__ import annotations

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_config
from app.models.company import Company
from app.models.contact_store import ContactStoreEntry
from app.models.employee import Employee
from app.models.misc import AppSettings, CreditLedgerEntry, Prompt, VerdictCacheEntry
from app.models.run import Run
from app.models.user import User

ALL_DOCUMENTS = [
    Run, Company, Employee, User,
    ContactStoreEntry, AppSettings, Prompt, VerdictCacheEntry, CreditLedgerEntry,
]

_client: AsyncIOMotorClient | None = None


async def init_db() -> None:
    global _client
    cfg = get_config()
    _client = AsyncIOMotorClient(cfg.mongo_uri)
    await init_beanie(database=_client[cfg.mongo_db], document_models=ALL_DOCUMENTS)


async def close_db() -> None:
    if _client is not None:
        _client.close()
