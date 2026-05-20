from __future__ import annotations

import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager

import chromadb
from fastapi import FastAPI

from backend.config import CHROMA_PATH
from backend.database import init_db
from backend.routers import chat as chat_router
from backend.routers import plan as plan_router
from backend.routers import profile as profile_router

logger = logging.getLogger(__name__)

_REQUIRED_ENV = {
    "OPENAI_API_KEY": "Required for plan generation, RAG retrieval, and chat responses.",
    "FASTAPI_BASE_URL": "Base URL used by the Streamlit frontend (defaults to http://localhost:8000).",
}
_PLACEHOLDER_PREFIXES = ("sk-your", "your-key", "")


def _check_env() -> None:
    """Log warnings for missing or placeholder environment variables."""
    all_ok = True
    for var, description in _REQUIRED_ENV.items():
        value = os.getenv(var, "")
        if not value or any(value.startswith(p) for p in _PLACEHOLDER_PREFIXES if p):
            logger.warning(
                "Environment variable %s is not set or still a placeholder. %s",
                var,
                description,
            )
            all_ok = False
    if all_ok:
        logger.info("All required environment variables are set.")


def _collection_populated(collection_name: str) -> bool:
    """Return True if the named Chroma collection exists and has at least one document."""
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        col = client.get_collection(collection_name)
        return col.count() > 0
    except Exception:
        return False


def _run_ingestion(module: str, label: str) -> None:
    """Run an ingestion module as a subprocess; log outcome."""
    logger.info("Running ingestion for %s ...", label)
    result = subprocess.run(
        [sys.executable, "-m", module],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        logger.info("%s ingestion complete: %s", label, result.stdout.strip())
    else:
        logger.warning(
            "%s ingestion failed (exit %d). "
            "Ensure OPENAI_API_KEY is set and re-run manually.\nstderr: %s",
            label,
            result.returncode,
            result.stderr.strip(),
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_env()
    init_db()

    # plans_kb
    if _collection_populated("plans_kb"):
        logger.info("plans_kb: collection ready.")
    else:
        logger.warning("plans_kb: collection missing or empty — running ingestion.")
        _run_ingestion("backend.ingestion.ingest_plans", "plans_kb")

    # chatbot_kb
    if _collection_populated("chatbot_kb"):
        logger.info("chatbot_kb: collection ready.")
    else:
        logger.warning("chatbot_kb: collection missing or empty — running ingestion.")
        _run_ingestion("backend.ingestion.ingest_chatbot", "chatbot_kb")

    yield


app = FastAPI(title="FitAI API", lifespan=lifespan)

app.include_router(profile_router.router)
app.include_router(plan_router.router)
app.include_router(chat_router.router)


@app.get("/")
def health_check():
    return {"status": "ok"}
