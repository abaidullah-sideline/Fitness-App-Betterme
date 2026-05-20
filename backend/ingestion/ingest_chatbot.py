"""Build chatbot_kb Chroma collection from PDFs, GIF metadata, and YouTube metadata."""

import sys
import pathlib
import uuid

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import chromadb
import pandas as pd
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from backend.config import OPENAI_API_KEY, CHROMA_PATH
from backend.database import get_connection

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
COLLECTION_NAME = "chatbot_kb"
PERSIST_DIR = str(PROJECT_ROOT / CHROMA_PATH / COLLECTION_NAME)
PDFS_DIR = PROJECT_ROOT / "data" / "knowledge" / "pdfs"
GIFS_DIR = PROJECT_ROOT / "data" / "knowledge" / "gifs"
YOUTUBE_CSV = PROJECT_ROOT / "data" / "knowledge" / "youtube_urls.csv"


def _embeddings() -> OpenAIEmbeddings:
    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-your"):
        sys.exit(
            "Error: OPENAI_API_KEY is not set. "
            "Add a valid key to your .env file and re-run."
        )
    return OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY, model="text-embedding-3-small")


def _chatbot_kb_populated() -> bool:
    if not pathlib.Path(PERSIST_DIR).exists():
        return False
    try:
        client = chromadb.PersistentClient(path=str(PROJECT_ROOT / CHROMA_PATH))
        col = client.get_collection(COLLECTION_NAME)
        return col.count() > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# PDF ingestion
# ---------------------------------------------------------------------------
def ingest_pdfs() -> int:
    """Embed all PDFs in data/knowledge/pdfs/ into chatbot_kb. Returns chunk count."""
    if not PDFS_DIR.exists():
        print(f"Warning: PDF directory not found at {PDFS_DIR}, skipping.")
        return 0

    pdf_files = list(PDFS_DIR.glob("*.pdf"))
    if not pdf_files:
        print("Warning: no PDF files found in data/knowledge/pdfs/, skipping.")
        return 0

    if _chatbot_kb_populated():
        print("chatbot_kb already exists, skipping PDF embedding.")
        return 0

    splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=64)
    all_docs = []
    for pdf_path in pdf_files:
        loader = PyPDFLoader(str(pdf_path))
        pages = loader.load()
        all_docs.extend(splitter.split_documents(pages))

    if not all_docs:
        return 0

    Chroma.from_documents(
        documents=all_docs,
        embedding=_embeddings(),
        collection_name=COLLECTION_NAME,
        persist_directory=PERSIST_DIR,
    )
    return len(all_docs)


# ---------------------------------------------------------------------------
# GIF metadata ingestion
# ---------------------------------------------------------------------------
def ingest_gifs() -> int:
    """Insert GIF metadata into SQLite gif_metadata table. Returns inserted count."""
    if not GIFS_DIR.exists():
        print(f"Warning: GIF directory not found at {GIFS_DIR}, skipping.")
        return 0

    gif_files = list(GIFS_DIR.glob("*.gif"))
    if not gif_files:
        print("Warning: no GIF files found in data/knowledge/gifs/, skipping.")
        return 0

    conn = get_connection()
    inserted = 0
    with conn:
        for gif_path in gif_files:
            relative_path = str(gif_path.relative_to(PROJECT_ROOT))
            already = conn.execute(
                "SELECT 1 FROM gif_metadata WHERE file_path = ?", (relative_path,)
            ).fetchone()
            if already:
                continue
            conn.execute(
                "INSERT INTO gif_metadata "
                "(gif_id, exercise_name, muscle_group, difficulty, file_path) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), gif_path.stem.replace("_", " "), "Unknown", "Unknown", relative_path),
            )
            inserted += 1
    conn.close()
    return inserted


# ---------------------------------------------------------------------------
# YouTube URL ingestion
# ---------------------------------------------------------------------------
def ingest_youtube() -> int:
    """Insert YouTube rows into SQLite youtube_resources table. Returns inserted count."""
    if not YOUTUBE_CSV.exists():
        print(f"Warning: youtube_urls.csv not found at {YOUTUBE_CSV}, skipping.")
        return 0

    df = pd.read_csv(YOUTUBE_CSV)
    required = {"title", "description", "url", "tags"}
    missing = required - set(df.columns)
    if missing:
        print(f"Warning: youtube_urls.csv missing columns {missing}, skipping.")
        return 0

    df = df.dropna(subset=["url"])
    if df.empty:
        print("Warning: no rows with valid URLs in youtube_urls.csv, skipping.")
        return 0

    conn = get_connection()
    inserted = 0
    with conn:
        for _, row in df.iterrows():
            already = conn.execute(
                "SELECT 1 FROM youtube_resources WHERE url = ?", (row["url"],)
            ).fetchone()
            if already:
                continue
            conn.execute(
                "INSERT INTO youtube_resources (title, description, url, tags) VALUES (?, ?, ?, ?)",
                (row.get("title"), row.get("description"), row["url"], row.get("tags")),
            )
            inserted += 1
    conn.close()
    return inserted


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    pdf_count = ingest_pdfs()
    gif_count = ingest_gifs()
    yt_count = ingest_youtube()

    print(f"chatbot_kb: {pdf_count} PDF chunks embedded.")
    print(f"gif_metadata: {gif_count} GIF entries inserted.")
    print(f"youtube_resources: {yt_count} YouTube entries inserted.")


if __name__ == "__main__":
    main()
