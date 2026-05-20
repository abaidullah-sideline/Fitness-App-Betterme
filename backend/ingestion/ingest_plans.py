"""Build plans_kb Chroma collection from data/dataset.csv."""

import os
import sys
import pathlib

import pandas as pd
import chromadb
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

# ---------------------------------------------------------------------------
# Resolve project root regardless of working directory
# ---------------------------------------------------------------------------
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import OPENAI_API_KEY, CHROMA_PATH  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
COLLECTION_NAME = "plans_kb"
DATASET_PATH = PROJECT_ROOT / "data" / "dataset.csv"
PERSIST_DIR = str(PROJECT_ROOT / CHROMA_PATH / COLLECTION_NAME)
TEMP_FILE = PROJECT_ROOT / "temp_descriptions.txt"


def _embeddings() -> OpenAIEmbeddings:
    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-your"):
        sys.exit(
            "Error: OPENAI_API_KEY is not set. "
            "Add a valid key to your .env file and re-run."
        )
    return OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY, model="text-embedding-3-small")


def _already_populated() -> bool:
    """Return True if plans_kb collection already has documents on disk."""
    persist_path = pathlib.Path(PERSIST_DIR)
    if not persist_path.exists():
        return False
    try:
        client = chromadb.PersistentClient(path=str(PROJECT_ROOT / CHROMA_PATH))
        col = client.get_collection(COLLECTION_NAME)
        return col.count() > 0
    except Exception:
        return False


def main() -> None:
    if _already_populated():
        print("plans_kb already exists, skipping.")
        return

    # ------------------------------------------------------------------
    # 1. Load dataset
    # ------------------------------------------------------------------
    if not DATASET_PATH.exists():
        sys.exit(f"Error: dataset not found at {DATASET_PATH}")

    df = pd.read_csv(DATASET_PATH)

    if "Semantic_Description" not in df.columns:
        sys.exit("Error: 'Semantic_Description' column missing from dataset.csv")

    descriptions = df["Semantic_Description"].dropna().tolist()

    # ------------------------------------------------------------------
    # 2. Write descriptions to temp file (one per line)
    # ------------------------------------------------------------------
    TEMP_FILE.write_text("\n".join(descriptions), encoding="utf-8")

    # ------------------------------------------------------------------
    # 3 & 4. Load with TextLoader + split one-chunk-per-description
    # ------------------------------------------------------------------
    loader = TextLoader(str(TEMP_FILE), encoding="utf-8")
    raw_docs = loader.load()

    # chunk_size=1 ensures one description per chunk: each description is
    # longer than 1 char so the merge algorithm never combines two lines.
    splitter = CharacterTextSplitter(
        chunk_size=1,
        chunk_overlap=0,
        separator="\n",
    )
    docs = splitter.split_documents(raw_docs)

    # ------------------------------------------------------------------
    # 5. Embed and persist to Chroma
    # ------------------------------------------------------------------
    embeddings = _embeddings()
    Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=PERSIST_DIR,
    )

    # ------------------------------------------------------------------
    # 6. Clean up temp file
    # ------------------------------------------------------------------
    TEMP_FILE.unlink(missing_ok=True)

    print(f"plans_kb: {len(docs)} documents embedded and persisted.")


if __name__ == "__main__":
    main()
