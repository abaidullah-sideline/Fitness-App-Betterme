# CLAUDE.md — FitAI Project Context

> This file is read automatically by Claude Code at the start of every session.
> Do not delete or rename it.

---

## Project Overview

FitAI is a personalised fitness and nutrition assistant. It generates a tailored 7-day workout and meal plan for each user using a **semantic recommendation engine** (NLP/LLM-based, no traditional ML classifiers), tracks daily completion, and provides on-demand guidance through an integrated RAG-powered chatbot.

The app has three pages: **Profile**, **Dashboard**, and **Chatbot**.

---

## Tech Stack & Packages

### Frontend
| Package | Version | Purpose |
|---|---|---|
| `streamlit` | latest | Rendering only — pages, tables, charts, chat UI |
| `streamlit-chat` | latest | Chat message components |

### Backend
| Package | Version | Purpose |
|---|---|---|
| `fastapi` | latest | All API endpoints — profile CRUD, plan gen, chat |
| `uvicorn` | latest | ASGI server for FastAPI |
| `pydantic` | v2 | Request/response validation schemas |

### AI & Orchestration
| Package | Version | Purpose |
|---|---|---|
| `langchain` | latest | Document loaders, text splitters, chains |
| `langchain-openai` | latest | OpenAI LLM + embeddings |
| `langchain-chroma` | latest | Chroma vector store integration |
| `langgraph` | latest | Chatbot state graph, memory, routing |
| `openai` | latest | Direct OpenAI API client |

### Data & Storage
| Package | Version | Purpose |
|---|---|---|
| `pandas` | latest | Dataset loading and filtering |
| `chromadb` | latest | Vector database (persisted to disk) |
| `sqlite3` | stdlib | User profiles, chat threads, checkpoints, logs |
| `python-dotenv` | latest | Load OPENAI_API_KEY from .env |

### Document Processing (RAG ingestion)
| Package | Version | Purpose |
|---|---|---|
| `pypdf` | latest | PDF text extraction |
| `pytube` or `yt-dlp` | latest | YouTube metadata extraction |

---

## Folder & File Structure

```
fitai/
├── CLAUDE.md                   ← this file
├── TASKS.md
├── PROMPTS.md
├── .env                        ← OPENAI_API_KEY (never commit)
├── .gitignore
├── requirements.txt
│
├── data/
│   ├── dataset.csv             ← synthetic fitness/meal plans (provided)
│   ├── knowledge/
│   │   ├── pdfs/               ← fitness & nutrition PDFs for RAG
│   │   ├── gifs/               ← exercise demonstration GIFs
│   │   └── youtube_urls.csv    ← columns: title, description, url, tags
│
├── backend/
│   ├── main.py                 ← FastAPI app entry point, mounts all routers
│   ├── config.py               ← settings, env vars, constants
│   ├── database.py             ← SQLite connection, table creation, helpers
│   │
│   ├── routers/
│   │   ├── profile.py          ← POST/GET/PUT /api/profile
│   │   ├── plan.py             ← GET /api/plan, POST /api/plan/edit, POST /api/plan/checkbox
│   │   └── chat.py             ← GET /api/chats, POST /api/chat, GET+DELETE /api/chat/{thread_id}
│   │
│   ├── services/
│   │   ├── recommender.py      ← semantic recommendation logic (Chroma + pandas filtering)
│   │   ├── plan_editor.py      ← NL plan editing via LLM
│   │   └── chatbot.py          ← LangGraph graph definition, RAG retrieval, memory
│   │
│   ├── schemas/
│   │   ├── profile.py          ← Pydantic models for profile
│   │   ├── plan.py             ← Pydantic models for plan, edit request
│   │   └── chat.py             ← Pydantic models for chat thread, message
│   │
│   └── ingestion/
│       ├── ingest_plans.py     ← Build plans_kb Chroma collection from dataset.csv
│       └── ingest_chatbot.py   ← Build chatbot_kb Chroma collection from PDFs/GIFs/YouTube
│
├── frontend/
│   ├── app.py                  ← Streamlit entry point, navigation bar, page routing
│   ├── api_client.py           ← All HTTP calls to FastAPI (single source of truth)
│   │
│   └── pages/
│       ├── profile.py          ← Profile page rendering
│       ├── dashboard.py        ← Dashboard page rendering
│       └── chat.py             ← Chatbot page rendering
│
└── chroma_db/                  ← Chroma persisted collections (git-ignored)
    ├── plans_kb/
    └── chatbot_kb/
```

---

## SQLite Schema

Database file: `fitai.db` (created automatically in project root).

```sql
-- User profiles
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    gender TEXT,
    age_group TEXT,
    bmi_category TEXT,
    fitness_goal TEXT,
    activity_level TEXT,
    dietary_preference TEXT,
    medical_conditions TEXT,
    allergies_intolerances TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Generated plans (stored as JSON blob)
CREATE TABLE IF NOT EXISTS plans (
    plan_id TEXT PRIMARY KEY,
    user_id TEXT,
    plan_json TEXT,           -- full 7-day plan as JSON string
    edit_history_json TEXT,   -- list of past edit commands (max 10)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Daily completion tracking
CREATE TABLE IF NOT EXISTS day_logs (
    log_id TEXT PRIMARY KEY,
    user_id TEXT,
    plan_id TEXT,
    day_of_week TEXT,         -- 'Monday', 'Tuesday', etc.
    is_complete INTEGER DEFAULT 0,
    completed_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Chat conversation threads
CREATE TABLE IF NOT EXISTS chat_threads (
    thread_id TEXT PRIMARY KEY,
    user_id TEXT,
    title TEXT,               -- first user message, truncated to 40 chars
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- LangGraph checkpoints (serialised graph state per thread)
CREATE TABLE IF NOT EXISTS chat_checkpoints (
    thread_id TEXT PRIMARY KEY,
    checkpoint_blob TEXT,     -- JSON-serialised LangGraph checkpoint
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Long-term memory summaries per user/thread
CREATE TABLE IF NOT EXISTS memory_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    thread_id TEXT,
    summary_text TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Dataset Schema (`data/dataset.csv`)

| Column | Type | Notes |
|---|---|---|
| `Plan_ID` | String | Unique identifier — present at the start of `Semantic_Description` |
| `Gender` | String | Used for hard filtering |
| `Age_Group` | String | |
| `BMI_Category` | String | |
| `Fitness_Goal` | String | Used for hard filtering |
| `Activity_Level` | String | |
| `Dietary_Preference` | String | Used for hard filtering |
| `Medical_Conditions` | String | |
| `Allergies_Intolerances` | String | |
| `Exercise_Schedule` | Text | Full weekly workout description |
| `Meal_Plan` | Text | Full weekly meal description |
| `Nutritional_Facts` | String | Nutrient breakdown string |
| `Est_Calories_Burned` | Integer | Estimated calories burned per day |
| `Semantic_Description` | Text | Rich NL summary of entire row — used for vector embedding |

---

## Key Conventions

### 1. Streamlit is render-only
- **No business logic in Streamlit files.** Every computation, AI call, DB read/write, and recommendation lives in the FastAPI backend.
- Streamlit pages only: call `api_client.py` functions → receive data → render it.
- All HTTP calls are centralised in `frontend/api_client.py`. Never call `requests` directly inside a page file.

### 2. Session state rules
- Use `st.session_state` for: current user_id, active page, active thread_id, profile completion status.
- Key names are constants defined at the top of `frontend/app.py`:
  ```python
  USER_ID_KEY = "user_id"
  PROFILE_COMPLETE_KEY = "profile_complete"
  ACTIVE_THREAD_KEY = "active_thread_id"
  ```
- Never store raw plan JSON or chat history in session_state — always fetch from the backend.

### 3. Navigation guard
- Dashboard tab is disabled (greyed out, non-clickable) until `st.session_state[PROFILE_COMPLETE_KEY] == True`.
- If a user navigates directly to `/dashboard` without a profile, redirect to Profile page with a warning banner.

### 4. Semantic recommendation approach
- Vector search uses `Chroma.similarity_search(user_query, k=20)`.
- `user_query` is built by `services/recommender.py` as a natural language sentence from profile fields.
- After vector search, apply hard pandas filters for `Gender`, `Fitness_Goal`, `Dietary_Preference` only.
- Skip a filter if the profile value is `"Any"` or `"All"`.
- Return the top-3 ranked results; use the highest-scoring as the active plan.

### 5. RAG pipeline (chatbot)
- Two separate Chroma collections: `plans_kb` (recommendation) and `chatbot_kb` (chatbot).
- `chatbot_kb` is built by `ingestion/ingest_chatbot.py` from PDFs, GIF metadata, and YouTube metadata.
- GIFs are **not** embedded as vectors. Their metadata (exercise name, muscle group, difficulty, file path) is stored in SQLite table `gif_metadata`. Retrieved by keyword match on exercise name.
- YouTube URLs stored in `youtube_urls.csv` and loaded into SQLite table `youtube_resources`. Retrieved by tag/keyword match.
- RAG is triggered only when the LangGraph router classifies the message topic as fitness/nutrition/workout.

### 6. LangGraph chatbot structure
```
Entry → Router → [RAG Retrieval → LLM] or [LLM only] → Memory Update → Response
```
- `StateGraph` nodes: `router`, `retrieve`, `generate`, `update_memory`
- State keys: `messages`, `user_profile`, `thread_id`, `retrieved_docs`, `memory_summary`
- Checkpoints saved to SQLite via `langgraph.checkpoint.sqlite.SqliteSaver`
- Long-term memory: after every session end (or every 5 turns), summarise the conversation and save to `memory_summaries` table.

### 7. Plan JSON structure
Plans are stored and exchanged as a JSON array of 7 day objects:
```json
[
  {
    "day": "Monday",
    "sr": 1,
    "workout_plan": "...",
    "breakfast": "...",
    "lunch": "...",
    "dinner": "...",
    "est_calories_burned": 350,
    "nutritional_facts": "Fat: 45g, Carbs: 210g, Protein: 80g, ..."
  }
]
```

### 8. Environment variables
All secrets loaded via `python-dotenv` in `backend/config.py`. Required:
```
OPENAI_API_KEY=sk-...
FASTAPI_BASE_URL=http://localhost:8000   # used by Streamlit api_client
```

### 9. Chroma initialisation
- Both Chroma collections are built **once** by running the ingestion scripts.
- On FastAPI startup (`backend/main.py` lifespan event), Chroma clients are loaded from disk (not rebuilt).
- If the collection does not exist on disk, the lifespan event runs the ingestion automatically.

### 10. Error handling pattern
- All FastAPI endpoints return structured error responses: `{"error": true, "message": "..."}` with appropriate HTTP status codes.
- `api_client.py` checks for error keys and surfaces them as `st.error(...)` banners in the UI.
- Never let raw exception tracebacks reach the Streamlit frontend.

---

## Running the Project

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# edit .env and add your OPENAI_API_KEY

# 3. Run ingestion (first time only)
python backend/ingestion/ingest_plans.py
python backend/ingestion/ingest_chatbot.py

# 4. Start backend
uvicorn backend.main:app --reload --port 8000

# 5. Start frontend (separate terminal)
streamlit run frontend/app.py
```
