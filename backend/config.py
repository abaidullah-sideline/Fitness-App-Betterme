import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
FASTAPI_BASE_URL: str = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")
DB_PATH: str = "fitai.db"
CHROMA_PATH: str = "chroma_db/"
