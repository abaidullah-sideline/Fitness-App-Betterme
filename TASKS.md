# TASKS.md — FitAI Build Checklist

> Tick boxes as features are completed. Work through phases in order.
> Each phase maps to one prompt in PROMPTS.md.

---

## Phase 0 — Project Scaffold & Configuration

- [ ] Create folder structure as defined in CLAUDE.md
- [ ] Create `requirements.txt` with all packages
- [ ] Create `.env.example` with placeholder keys
- [ ] Create `.gitignore` (ignore `.env`, `chroma_db/`, `fitai.db`, `__pycache__/`, `.venv/`)
- [ ] Create `backend/config.py` — load `.env`, export constants (`OPENAI_API_KEY`, `FASTAPI_BASE_URL`, `DB_PATH`, `CHROMA_PATH`)
- [ ] Create `backend/database.py` — SQLite connection helper, `init_db()` function that creates all 7 tables on first run
- [ ] Verify `init_db()` runs without errors and creates `fitai.db`

---

## Phase 1 — Data Ingestion: Plans Knowledge Base

- [ ] Create `backend/ingestion/ingest_plans.py`
- [ ] Load `data/dataset.csv` with pandas
- [ ] Save `Semantic_Description` column to `temp_descriptions.txt` (one description per line)
- [ ] Use `TextLoader` + `CharacterTextSplitter` (chunk_size=0, overlap=0, separator=`\n`) to split into one chunk per description
- [ ] Initialise `Chroma` collection `plans_kb` with `OpenAIEmbeddings`, persist to `chroma_db/plans_kb/`
- [ ] Print confirmation: number of documents embedded
- [ ] Verify collection is reloadable from disk without re-embedding

---

## Phase 2 — Data Ingestion: Chatbot Knowledge Base

- [ ] Create `backend/ingestion/ingest_chatbot.py`
- [ ] Load all PDFs from `data/knowledge/pdfs/` using `PyPDFLoader`; chunk with `RecursiveCharacterTextSplitter` (chunk_size=512, overlap=64)
- [ ] Create SQLite table `gif_metadata` (gif_id, exercise_name, muscle_group, difficulty, file_path)
- [ ] Parse GIF filenames from `data/knowledge/gifs/` and insert metadata rows into `gif_metadata`
- [ ] Create SQLite table `youtube_resources` (id, title, description, url, tags)
- [ ] Load `data/knowledge/youtube_urls.csv` and insert rows into `youtube_resources`
- [ ] Embed all PDF chunks into Chroma collection `chatbot_kb`, persist to `chroma_db/chatbot_kb/`
- [ ] Print confirmation: PDF chunks embedded, GIF entries inserted, YouTube entries inserted

---

## Phase 3 — Backend: Profile API

- [ ] Create `backend/schemas/profile.py` — Pydantic models: `ProfileCreate`, `ProfileUpdate`, `ProfileResponse`
- [ ] Create `backend/routers/profile.py` with three endpoints:
  - [ ] `POST /api/profile` — insert into `users` table, return `user_id`
  - [ ] `GET /api/profile` — fetch profile by `user_id` (query param)
  - [ ] `PUT /api/profile` — update profile, set `updated_at`
- [ ] Mount profile router in `backend/main.py`
- [ ] Test all three endpoints with curl or a REST client

---

## Phase 4 — Backend: Semantic Recommendation Service

- [ ] Create `backend/services/recommender.py`
- [ ] Implement `build_user_query(profile: dict) -> str` — converts profile fields to a NL sentence
- [ ] Implement `get_recommendations(profile: dict) -> list[dict]` function:
  - [ ] Load `plans_kb` Chroma collection from disk
  - [ ] Run `similarity_search(user_query, k=20)`
  - [ ] Extract `Plan_ID` from each returned document
  - [ ] Filter DataFrame by Plan_IDs, then apply hard filters (Gender, Fitness_Goal, Dietary_Preference)
  - [ ] Return top-3 plans (Exercise_Schedule, Meal_Plan, Nutritional_Facts, Est_Calories_Burned)
- [ ] Implement `parse_plan_to_days(plan: dict) -> list[dict]` — converts flat plan fields to 7-day JSON array (see CLAUDE.md plan structure)

---

## Phase 5 — Backend: Plan API

- [ ] Create `backend/schemas/plan.py` — Pydantic models: `PlanResponse`, `PlanEditRequest`, `CheckboxRequest`
- [ ] Create `backend/routers/plan.py` with endpoints:
  - [ ] `GET /api/plan` — call recommender service, store plan in `plans` table, return 7-day plan JSON
  - [ ] `POST /api/plan/edit` — accept `{user_id, edit_command, current_plan}`, call `plan_editor.py`, patch and return updated plan; append command to `edit_history_json` (max 10)
  - [ ] `POST /api/plan/checkbox` — toggle `is_complete` in `day_logs`, return updated daily stats (calories, macros)
- [ ] Create `backend/services/plan_editor.py` — `edit_plan(current_plan: list, command: str) -> list` using an LLM call with the plan as context
- [ ] Mount plan router in `backend/main.py`
- [ ] Test plan generation end-to-end with a sample profile

---

## Phase 6 — Backend: Chatbot Service (LangGraph)

- [ ] Create `backend/services/chatbot.py`
- [ ] Define `GraphState` TypedDict: `messages`, `user_profile`, `thread_id`, `retrieved_docs`, `memory_summary`
- [ ] Implement node functions:
  - [ ] `router_node` — classify message topic; set retrieval flag
  - [ ] `retrieve_node` — query `chatbot_kb` Chroma, fetch GIF metadata and YouTube links from SQLite
  - [ ] `generate_node` — LLM call with system prompt (user profile + memory summary + retrieved docs)
  - [ ] `update_memory_node` — every 5 turns, summarise conversation and upsert `memory_summaries`
- [ ] Build `StateGraph`, add nodes and edges, compile graph
- [ ] Set up `SqliteSaver` checkpoint with `fitai.db`
- [ ] Implement `run_chat(user_id, thread_id, message) -> str` — entry point called by the router

---

## Phase 7 — Backend: Chat API

- [ ] Create `backend/schemas/chat.py` — Pydantic models: `ChatMessageRequest`, `ChatMessageResponse`, `ThreadSummary`
- [ ] Create `backend/routers/chat.py` with endpoints:
  - [ ] `GET /api/chats` — list all threads for `user_id` (thread_id, title, updated_at)
  - [ ] `POST /api/chat` — call `run_chat()`, save/update thread record, return AI response
  - [ ] `GET /api/chat/{thread_id}` — load full message history from checkpoint
  - [ ] `DELETE /api/chat/{thread_id}` — delete thread, checkpoint, and memory summary
- [ ] Mount chat router in `backend/main.py`
- [ ] Add FastAPI lifespan event: on startup, load Chroma collections from disk (auto-ingest if missing)

---

## Phase 8 — Frontend: Streamlit App Shell & Navigation

- [ ] Create `frontend/api_client.py` — one function per API endpoint; all use `requests` pointed at `FASTAPI_BASE_URL`
- [ ] Create `frontend/app.py`:
  - [ ] Initialise session state keys on first load
  - [ ] Render persistent navigation bar (Profile / Dashboard / Chatbot tabs)
  - [ ] Disable Dashboard tab if `profile_complete == False`
  - [ ] Route to correct page file based on active tab
- [ ] Verify tab switching works without page reload side-effects

---

## Phase 9 — Frontend: Profile Page

- [ ] Create `frontend/pages/profile.py`
- [ ] If no profile in session: render onboarding form modal (all 8 fields, correct input types)
- [ ] Validate required fields before allowing submission
- [ ] On submit: call `api_client.create_profile()`, store `user_id` in session state, set `profile_complete = True`
- [ ] After submission: render read-only profile card showing all 8 fields
- [ ] Implement Edit button — re-opens form pre-filled with current values
- [ ] On edit save: call `api_client.update_profile()`, show "Your plan is being updated" banner

---

## Phase 10 — Frontend: Dashboard Page

- [ ] Create `frontend/pages/dashboard.py`
- [ ] On page load: call `api_client.get_plan()`, display loading spinner during fetch
- [ ] Render weekly plan as a styled table (Sr., Checkbox, Day, Workout Plan, Breakfast, Lunch, Dinner columns)
- [ ] Highlight today's row
- [ ] Long workout text (>80 chars) is collapsible via `st.expander`
- [ ] Checkbox interaction: call `api_client.toggle_checkbox()`, re-render dashboard section
- [ ] Render NL edit search bar below table; on submit call `api_client.edit_plan()`; highlight changed cells in amber for 3 seconds
- [ ] Show "Reset to original plan" button
- [ ] When a day is checked: render daily dashboard below table (metric cards: calories, fat, carbs, protein, calcium, vitamins)
- [ ] Render macros donut/bar chart (Streamlit native chart)
- [ ] Render weekly completion progress bar

---

## Phase 11 — Frontend: Chatbot Page

- [ ] Create `frontend/pages/chat.py`
- [ ] Render two-column layout: sidebar (thread list) + main chat panel
- [ ] Sidebar: "New chat" button at top; list threads from `api_client.get_chats()`; active thread highlighted
- [ ] Main panel: render message history (user + assistant bubbles) from `api_client.get_thread()`
- [ ] Text input + Send button at bottom of main panel
- [ ] On send: call `api_client.send_message()`, append response to chat history, re-render
- [ ] Show streaming indicator ("thinking...") while waiting for response
- [ ] AI responses containing YouTube URLs rendered as clickable links
- [ ] AI responses containing GIF references rendered with `st.image()`

---

## Phase 12 — Integration Testing & Polish

- [ ] End-to-end test: create profile → generate plan → tick checkbox → view dashboard metrics
- [ ] End-to-end test: edit plan with NL command → verify diff highlights → reset to original
- [ ] End-to-end test: open chatbot → send a workout question → verify RAG retrieval used → check GIF/video appears
- [ ] End-to-end test: close browser → reopen → verify chat history persists, profile persists
- [ ] Verify Dashboard tab is locked until profile is complete
- [ ] Verify all `st.error()` banners appear correctly on API failures
- [ ] Check `.env` secrets are never printed or exposed in any Streamlit page
- [ ] Write final `README.md` with setup instructions

---

## Phase 13 — Optional Enhancements (post-MVP)

- [ ] Add plan comparison: show top-3 matched plans side by side before confirming
- [ ] Add weekly summary email (stretch goal)
- [ ] Add dark/light theme toggle in Streamlit
- [ ] Add export plan as PDF button
- [ ] Add user avatar / initials display on Profile page
