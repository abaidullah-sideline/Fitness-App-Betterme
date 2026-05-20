# FitAI — Personalised Fitness & Nutrition Assistant

FitAI generates a tailored 7-day workout and meal plan for each user using a semantic recommendation engine (RAG + LLM), tracks daily completion, and provides on-demand guidance through an integrated AI chatbot.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10 or higher |
| OpenAI API key | Required for embeddings, plan generation, and chat |

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```
OPENAI_API_KEY=sk-...          # Required
FASTAPI_BASE_URL=http://localhost:8000   # Leave as-is for local development
```

> **Never commit `.env` to version control.** It is already listed in `.gitignore`.

### 3. Run knowledge-base ingestion (first time only)

These scripts embed your fitness documents and build the Chroma vector stores.

```bash
# Build the plan recommendation index from data/dataset.csv
python -m backend.ingestion.ingest_plans

# Build the chatbot knowledge base from PDFs, GIFs, and YouTube metadata
python -m backend.ingestion.ingest_chatbot
```

Both scripts are idempotent — re-running them skips embedding if the collection already exists.

**What to place in `data/knowledge/` before running `ingest_chatbot`:**

| Path | Content |
|---|---|
| `data/knowledge/pdfs/` | Fitness and nutrition PDF documents |
| `data/knowledge/gifs/` | Exercise demonstration GIF files |
| `data/knowledge/youtube_urls.csv` | Columns: `title, description, url, tags` |

The ingestion scripts also run automatically on FastAPI startup if a collection is missing or empty.

### 4. Start the backend

```bash
uvicorn backend.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Visit `http://localhost:8000/docs` for the interactive Swagger UI.

### 5. Start the frontend (separate terminal)

```bash
streamlit run frontend/app.py
```

The app will open at `http://localhost:8501`.

---

## Pages

### Profile

Set up your personal details: gender, age group, BMI category, fitness goal, activity level, dietary preference, medical conditions, and allergies. This information drives the recommendation engine.

- First visit: onboarding form centred on the page.
- After setup: read-only profile card with an **Edit profile** button.
- Editing your profile triggers a fresh plan to be generated on the next Dashboard visit.

### Dashboard

Displays your personalised 7-day workout and meal plan.

- **Weekly table** — one row per day with workout, breakfast, lunch, and dinner. Today's row is highlighted. Long workout descriptions are collapsed into an expandable section.
- **Completion checkboxes** — tick each day to mark it complete. Daily nutrition stats (calories, macros, donut chart) appear below the table for each checked day.
- **Plan editor** — type a natural-language instruction (e.g. *"Replace Wednesday workout with yoga"*) and click **Apply**. Click **Reset to original** to restore the AI-generated plan.

### Chatbot

An AI fitness and nutrition assistant backed by RAG retrieval.

- **Thread sidebar** — lists all previous conversations. Click any thread to reload its history. Use **New chat** to start a fresh conversation.
- **Chat panel** — type questions about workouts, meals, or nutrition. The assistant retrieves relevant content from the knowledge base (PDFs, GIF metadata, YouTube resources) when the topic is fitness-related.
- Responses may include inline YouTube links and exercise GIF images sourced from the knowledge base.
- Chat history and long-term memory summaries are persisted to SQLite, so conversations resume after restarting the app.

---

## Project Structure

```
fitai/
├── backend/
│   ├── main.py              FastAPI entry point
│   ├── config.py            Environment variables and constants
│   ├── database.py          SQLite setup and helpers
│   ├── routers/             API route handlers (profile, plan, chat)
│   ├── services/            Business logic (recommender, chatbot, plan editor)
│   ├── schemas/             Pydantic request/response models
│   └── ingestion/           Knowledge-base ingestion scripts
├── frontend/
│   ├── app.py               Streamlit entry point and navigation
│   ├── api_client.py        All HTTP calls to the backend
│   └── pages/               Profile, Dashboard, and Chatbot page modules
├── data/
│   ├── dataset.csv          Fitness/meal plan dataset
│   └── knowledge/           PDFs, GIFs, and YouTube metadata for RAG
├── chroma_db/               Persisted Chroma vector collections (git-ignored)
├── fitai.db                 SQLite database (git-ignored)
├── .env                     Secrets — never commit (git-ignored)
└── requirements.txt
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `OPENAI_API_KEY` not set | Add the key to `.env` and restart the backend |
| `plans_kb` or `chatbot_kb` missing | Run the ingestion scripts manually (see Step 3) |
| Backend not reachable from frontend | Ensure `FASTAPI_BASE_URL` in `.env` matches the running uvicorn port |
| `ModuleNotFoundError: backend` | Run all commands from the project root directory |
