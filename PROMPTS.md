# PROMPTS.md — Claude Code Prompts by Phase

> Paste each prompt into Claude Code to complete the corresponding phase.
> Complete phases in order. Tick off tasks in TASKS.md as you go.
> Always start a new Claude Code session by letting it read CLAUDE.md first.

---

## Phase 0 — Project Scaffold & Configuration

```
Read CLAUDE.md fully before starting.

Scaffold the complete FitAI project. Do the following:

1. Create the full folder and file structure exactly as described in the "Folder & File Structure" section of CLAUDE.md. Create empty placeholder files (with a one-line comment) for every file listed.

2. Create requirements.txt with every package listed in the "Tech Stack & Packages" section of CLAUDE.md.

3. Create .env.example with:
   OPENAI_API_KEY=sk-your-key-here
   FASTAPI_BASE_URL=http://localhost:8000

4. Create .gitignore that ignores: .env, chroma_db/, fitai.db, __pycache__/, .venv/, *.pyc, .DS_Store

5. Implement backend/config.py:
   - Load .env using python-dotenv
   - Export constants: OPENAI_API_KEY, FASTAPI_BASE_URL, DB_PATH (= "fitai.db"), CHROMA_PATH (= "chroma_db/")

6. Implement backend/database.py:
   - SQLite connection helper function get_connection() that returns a sqlite3.Connection
   - init_db() function that creates all 7 tables defined in the "SQLite Schema" section of CLAUDE.md
   - Also create tables: gif_metadata (gif_id TEXT PK, exercise_name TEXT, muscle_group TEXT, difficulty TEXT, file_path TEXT) and youtube_resources (id INTEGER PK AUTOINCREMENT, title TEXT, description TEXT, url TEXT, tags TEXT)
   - Call init_db() when the module is imported

7. Add a __main__ block to backend/database.py that prints "Database initialised successfully" and lists all created tables.

Run python backend/database.py to verify it works.
```

---

## Phase 1 — Data Ingestion: Plans Knowledge Base

```
Read CLAUDE.md fully before starting.

Implement backend/ingestion/ingest_plans.py. This script builds the semantic vector index for the plan recommendation engine.

Requirements:
1. Load data/dataset.csv using pandas.
2. Save the Semantic_Description column to a temporary file temp_descriptions.txt, one description per line.
3. Use LangChain TextLoader to load temp_descriptions.txt.
4. Use CharacterTextSplitter with chunk_size=0, chunk_overlap=0, separator="\n" so each description is a single chunk.
5. Initialise a Chroma vector database named "plans_kb" using OpenAIEmbeddings(). Persist it to chroma_db/plans_kb/ as defined in config.py CHROMA_PATH.
6. Delete temp_descriptions.txt after embedding.
7. Print: "plans_kb: {n} documents embedded and persisted."
8. Add a guard so re-running the script checks if the collection already has documents and skips re-embedding (print "plans_kb already exists, skipping." instead).

Use OPENAI_API_KEY from config.py. Handle missing API key with a clear error message.

Run the script and confirm it embeds without errors.
```

---

## Phase 2 — Data Ingestion: Chatbot Knowledge Base

```
Read CLAUDE.md fully before starting.

Implement backend/ingestion/ingest_chatbot.py. This script builds the chatbot RAG knowledge base from three sources: PDFs, GIF metadata, and YouTube URLs.

Requirements:

PDF ingestion:
1. Load all .pdf files from data/knowledge/pdfs/ using PyPDFLoader (iterate the directory).
2. Chunk each PDF using RecursiveCharacterTextSplitter with chunk_size=512, chunk_overlap=64.
3. Embed all chunks into a Chroma collection named "chatbot_kb", persisted to chroma_db/chatbot_kb/.
4. Skip re-embedding if collection already exists and has documents.

GIF metadata ingestion:
5. Scan all .gif files in data/knowledge/gifs/.
6. Parse each filename as the exercise name (replace underscores with spaces, strip extension).
7. Insert a row into the gif_metadata SQLite table for each GIF: gif_id = UUID, exercise_name = parsed name, muscle_group = "Unknown", difficulty = "Unknown", file_path = relative path.
8. Skip inserting if the file_path already exists in the table.

YouTube URL ingestion:
9. Load data/knowledge/youtube_urls.csv (columns: title, description, url, tags).
10. Insert each row into the youtube_resources SQLite table. Skip duplicates by url.

Print a summary:
- "chatbot_kb: {n} PDF chunks embedded."
- "gif_metadata: {n} GIF entries inserted."
- "youtube_resources: {n} YouTube entries inserted."

Handle missing directories gracefully (print a warning and continue).
```

---

## Phase 3 — Backend: Profile API

```
Read CLAUDE.md fully before starting.

Implement the Profile API in three files.

1. backend/schemas/profile.py — Pydantic v2 models:
   - ProfileCreate: all 8 fields (gender, age_group, bmi_category, fitness_goal, activity_level, dietary_preference, medical_conditions, allergies_intolerances). All strings. medical_conditions and allergies_intolerances default to "None".
   - ProfileUpdate: same fields, all Optional.
   - ProfileResponse: same as ProfileCreate plus user_id, created_at, updated_at.

2. backend/routers/profile.py — FastAPI router with prefix "/api":
   - POST /api/profile: accept ProfileCreate body. Generate a UUID for user_id. Insert into users table. Return ProfileResponse.
   - GET /api/profile: accept user_id as query param. Fetch from users table. Return ProfileResponse or 404.
   - PUT /api/profile: accept user_id as query param + ProfileUpdate body. Update changed fields + set updated_at. Return updated ProfileResponse.
   All endpoints return {"error": true, "message": "..."} with appropriate HTTP status on failure.

3. backend/main.py — FastAPI app:
   - Call init_db() on startup via lifespan event.
   - Include the profile router.
   - Add a GET / health check that returns {"status": "ok"}.

Test with: curl -X POST http://localhost:8000/api/profile -H "Content-Type: application/json" -d '{"gender":"Male","age_group":"26-35","bmi_category":"Normal","fitness_goal":"Muscle Gain","activity_level":"Moderately Active","dietary_preference":"No Preference"}'
```

---

## Phase 4 — Backend: Semantic Recommendation Service

```
Read CLAUDE.md fully before starting.

Implement backend/services/recommender.py. This is the core NLP recommendation engine.

Requirements:

1. build_user_query(profile: dict) -> str
   Convert a user profile dict into a natural language sentence for vector search.
   Example output: "A 26-35 year old male with Normal BMI looking to gain muscle. Moderately active with no dietary restrictions. No known medical conditions or allergies."
   Use all 8 profile fields meaningfully in the sentence.

2. get_recommendations(profile: dict) -> list[dict]
   - Load the plans_kb Chroma collection from disk (CHROMA_PATH from config.py). Do not re-embed.
   - Call similarity_search(user_query, k=20) on the Chroma collection.
   - Extract Plan_ID from each returned document's page_content (Plan_ID is the first token before a space or colon on the first line of the Semantic_Description).
   - Load data/dataset.csv into a pandas DataFrame.
   - Filter the DataFrame to rows whose Plan_ID is in the extracted list.
   - Apply hard pandas filters: match Gender, Fitness_Goal, Dietary_Preference columns against profile. Skip a filter if the profile value is "Any" or "All".
   - Return the top 3 matching rows as a list of dicts with keys: Plan_ID, Exercise_Schedule, Meal_Plan, Nutritional_Facts, Est_Calories_Burned.

3. parse_plan_to_days(plan: dict) -> list[dict]
   Parse Exercise_Schedule and Meal_Plan text fields into a 7-element list of day objects matching the plan JSON structure defined in CLAUDE.md (keys: day, sr, workout_plan, breakfast, lunch, dinner, est_calories_burned, nutritional_facts).
   - Days: Monday through Sunday.
   - If parsing cannot split into 7 days cleanly, distribute content evenly and log a warning.
   - est_calories_burned and nutritional_facts are the same for all days (from the plan row).
```

---

## Phase 5 — Backend: Plan API

```
Read CLAUDE.md fully before starting.

Implement the Plan API.

1. backend/schemas/plan.py — Pydantic v2 models:
   - DayPlan: day, sr, workout_plan, breakfast, lunch, dinner, est_calories_burned, nutritional_facts
   - PlanResponse: plan_id, user_id, days (list[DayPlan]), created_at
   - PlanEditRequest: user_id (str), edit_command (str), current_plan (list[DayPlan])
   - CheckboxRequest: user_id (str), plan_id (str), day_of_week (str), is_complete (bool)
   - DailyStats: day_of_week, est_calories_burned, fat_g, carbs_g, protein_g, nutritional_facts

2. backend/services/plan_editor.py — implement edit_plan(current_plan: list, command: str) -> list:
   - Convert current_plan to a compact JSON string.
   - Call the OpenAI LLM with a system prompt: "You are a fitness plan editor. Given a 7-day JSON plan and an edit command, return the modified plan as valid JSON only, same structure, no explanation."
   - Parse the response as JSON and return the updated list of day dicts.
   - On parse failure, return the original plan unchanged and log the error.

3. backend/routers/plan.py — FastAPI router with prefix "/api":
   - GET /api/plan: accept user_id as query param. Fetch profile from DB. Call get_recommendations() then parse_plan_to_days(). Store plan in plans table (plan_json as JSON string). Return PlanResponse. If a plan already exists for this user and profile hasn't been updated since, return the cached plan.
   - POST /api/plan/edit: call edit_plan(), update plan_json in DB, append command to edit_history_json (keep max 10 entries), return updated PlanResponse.
   - POST /api/plan/checkbox: toggle is_complete in day_logs. Return DailyStats parsed from the day's nutritional_facts string.
   - POST /api/plan/reset: restore plan_json to the originally generated plan (store original separately as original_plan_json in plans table).

4. Mount plan router in backend/main.py.

Test GET /api/plan with the user_id created in Phase 3.
```

---

## Phase 6 — Backend: Chatbot Service (LangGraph)

```
Read CLAUDE.md fully before starting.

Implement backend/services/chatbot.py using LangGraph.

Requirements:

1. Define GraphState as a TypedDict:
   messages: list (LangChain message objects)
   user_profile: dict
   thread_id: str
   retrieved_docs: list[str]
   memory_summary: str
   turn_count: int

2. Implement these node functions:

   router_node(state): 
   - Look at the last user message.
   - Use a short LLM call (or keyword heuristic) to classify: is topic fitness/nutrition/workout? Set a flag in state. Return updated state.

   retrieve_node(state):
   - Query chatbot_kb Chroma (k=3) with the last user message.
   - Also query gif_metadata SQLite table with a keyword match on the message for exercise names.
   - Also query youtube_resources SQLite table with a keyword match on tags/title.
   - Populate state["retrieved_docs"] with text chunks + any GIF file paths + YouTube URLs.

   generate_node(state):
   - Build system prompt: include user profile summary, memory_summary, and (if retrieved_docs) the retrieved content.
   - Call ChatOpenAI with the full messages list.
   - Append the AI response to state["messages"].
   - Increment state["turn_count"].

   update_memory_node(state):
   - Trigger only if turn_count % 5 == 0.
   - Summarise the last 10 messages using an LLM call.
   - Upsert to memory_summaries table in SQLite.
   - Update state["memory_summary"].

3. Build the StateGraph:
   - Nodes: router, retrieve, generate, update_memory
   - Edges: router → retrieve (if fitness topic) or generate (if not) → update_memory → END
   - Compile with SqliteSaver checkpointer pointed at fitai.db

4. Implement run_chat(user_id: str, thread_id: str, message: str) -> str:
   - Load memory_summary from SQLite for this user+thread (empty string if none).
   - Load user profile from SQLite.
   - Invoke the graph with config={"configurable": {"thread_id": thread_id}}.
   - Return the last assistant message content.
```

---

## Phase 7 — Backend: Chat API

```
Read CLAUDE.md fully before starting.

Implement the Chat API.

1. backend/schemas/chat.py — Pydantic v2 models:
   - ChatMessageRequest: user_id (str), thread_id (str | None = None), message (str)
   - ChatMessageResponse: thread_id (str), response (str), retrieved_sources (list[str])
   - ThreadSummary: thread_id (str), title (str), updated_at (str)
   - MessageHistory: thread_id (str), messages (list[dict])

2. backend/routers/chat.py — FastAPI router with prefix "/api":
   - GET /api/chats: accept user_id query param. Return list[ThreadSummary] ordered by updated_at desc.
   - POST /api/chat: 
     - If thread_id is None, generate a new UUID and insert a new row into chat_threads (title = first 40 chars of message).
     - Call run_chat(user_id, thread_id, message).
     - Update chat_threads.updated_at.
     - Return ChatMessageResponse.
   - GET /api/chat/{thread_id}: load checkpoint from SqliteSaver, extract messages list, return MessageHistory.
   - DELETE /api/chat/{thread_id}: delete from chat_threads, chat_checkpoints, memory_summaries.

3. Mount chat router in backend/main.py.

4. Update the FastAPI lifespan event in main.py:
   - On startup: attempt to load plans_kb and chatbot_kb Chroma collections.
   - If either collection is missing or empty, automatically run the corresponding ingestion script as a subprocess.
   - Log startup status for each collection.
```

---

## Phase 8 — Frontend: Streamlit App Shell & Navigation

```
Read CLAUDE.md fully before starting.

Implement the Streamlit frontend shell.

1. frontend/api_client.py — implement one function per backend endpoint using the requests library. Base URL from FASTAPI_BASE_URL in config.py. Functions:
   - create_profile(data: dict) -> dict
   - get_profile(user_id: str) -> dict
   - update_profile(user_id: str, data: dict) -> dict
   - get_plan(user_id: str) -> dict
   - edit_plan(user_id: str, command: str, current_plan: list) -> dict
   - toggle_checkbox(user_id: str, plan_id: str, day: str, is_complete: bool) -> dict
   - reset_plan(user_id: str) -> dict
   - get_chats(user_id: str) -> list
   - send_message(user_id: str, thread_id: str | None, message: str) -> dict
   - get_thread(thread_id: str) -> dict
   - delete_thread(thread_id: str) -> bool
   Each function catches request exceptions and returns {"error": True, "message": str(e)} on failure.

2. frontend/app.py:
   - On first load, initialise session state: USER_ID_KEY = None, PROFILE_COMPLETE_KEY = False, ACTIVE_THREAD_KEY = None, ACTIVE_PAGE_KEY = "Profile".
   - Render a top navigation bar with three tabs: Profile, Dashboard, Chatbot.
   - Dashboard tab is disabled (st.button with disabled=True) if profile_complete is False.
   - Route to the correct page module based on ACTIVE_PAGE_KEY.
   - If user navigates to Dashboard without a profile: redirect to Profile page and show st.warning("Please complete your profile first.").

Test that the app loads, tabs render, and the Dashboard tab is disabled before profile creation.
```

---

## Phase 9 — Frontend: Profile Page

```
Read CLAUDE.md fully before starting.

Implement frontend/pages/profile.py.

Behaviour:
- If st.session_state["user_id"] is None (no profile yet): render an onboarding form. The form should feel like a clean modal/card overlay, centred on the page, with a title "Set up your profile".
- Form fields (use the exact input types from CLAUDE.md section 4.1):
  - Gender: st.radio with options Male / Female / Non-binary / Prefer not to say
  - Age Group: st.selectbox
  - BMI Category: st.selectbox
  - Fitness Goal: st.selectbox
  - Activity Level: st.selectbox
  - Dietary Preference: st.selectbox
  - Medical Conditions: st.text_area (placeholder: "e.g. Diabetes, Hypertension — leave blank if none")
  - Allergies/Intolerances: st.text_area (placeholder: "e.g. Lactose, Gluten — leave blank if none")
- Validate that the first 6 fields are not empty/unselected before allowing submission. Show st.error() inline for each missing required field.
- On valid submit: call api_client.create_profile(data). On success, store user_id in session state, set profile_complete = True, st.rerun() to refresh the page.
- If user_id exists: render a read-only profile card showing all 8 fields in a two-column layout.
- Show an "Edit profile" button. Clicking it sets an edit_mode flag in session state and re-renders the form pre-filled with current values.
- On edit save: call api_client.update_profile(). Show st.info("Your plan is being updated...") banner. Clear the edit_mode flag.
```

---

## Phase 10 — Frontend: Dashboard Page

```
Read CLAUDE.md fully before starting.

Implement frontend/pages/dashboard.py.

Requirements:
1. On page load, call api_client.get_plan(user_id). Show st.spinner("Generating your personalised plan...") during the call. Cache the result in st.session_state["current_plan"] to avoid re-fetching on every rerender.

2. Render the weekly plan as an interactive table:
   - Columns: ☑ (checkbox), Sr., Day, Workout Plan, Breakfast, Lunch, Dinner
   - Use st.columns() to lay out each row.
   - Today's day name (datetime.now().strftime("%A")) gets a highlighted background using st.markdown with a coloured container.
   - Workout text longer than 80 characters: wrap in st.expander("See full workout").
   - Each day's checkbox is a st.checkbox keyed by day name. On change: call api_client.toggle_checkbox() and update st.session_state["day_logs"].

3. Below the table, render a natural language edit bar:
   - st.text_input("Modify your plan", placeholder="e.g. Replace Wednesday workout with yoga")
   - "Apply" button. On click: call api_client.edit_plan(command). Update st.session_state["current_plan"] with the returned plan.
   - Show "Reset to original plan" button that calls api_client.reset_plan() and refreshes.

4. Below the edit bar, for each day that is checked, render a daily stats section:
   - Show four st.metric() cards: Calories Burned, Fat (g), Carbohydrates (g), Protein (g).
   - Parse these from the DailyStats response returned by the checkbox endpoint.
   - Render a st.bar_chart() or st.pyplot() donut chart of the macros breakdown.
   - Render a st.progress() bar for weekly completion (days_complete / 7).
```

---

## Phase 11 — Frontend: Chatbot Page

```
Read CLAUDE.md fully before starting.

Implement frontend/pages/chat.py.

Requirements:
1. Two-column layout: use st.columns([1, 3]).

2. Left column (sidebar):
   - "New chat" button at the top. On click: clear ACTIVE_THREAD_KEY from session state, clear st.session_state["chat_messages"].
   - Call api_client.get_chats(user_id). Render each thread as a clickable st.button (label = thread title). Active thread is highlighted. On click: set ACTIVE_THREAD_KEY, call api_client.get_thread(thread_id), load messages into st.session_state["chat_messages"].

3. Right column (main chat panel):
   - Render message history from st.session_state["chat_messages"]. User messages right-aligned, assistant messages left-aligned. Use st.chat_message() components.
   - For assistant messages: scan the message text for YouTube URLs (http/https links) and render them as st.markdown clickable links. Scan for GIF file paths (ending in .gif) and render them with st.image().
   - At the bottom: st.chat_input("Ask about workouts, meals, or nutrition...").
   - On submit: append user message to session state immediately (optimistic UI). Call api_client.send_message(). While waiting, show st.spinner("Thinking..."). Append AI response to session state. st.rerun().

4. If no user_id in session state: show st.info("Complete your profile to get personalised responses.") but still allow chatting (send profile as empty dict in that case).
```

---

## Phase 12 — Integration Testing & Polish

```
Read CLAUDE.md fully before starting.

Perform final integration testing and polish. Work through the following checklist:

Testing:
1. Run the full user journey: create profile → navigate to dashboard → verify plan loads → tick Monday checkbox → verify stats appear.
2. Enter an NL edit command ("make Tuesday's workout lighter") → verify plan updates → click Reset → verify plan restores.
3. Open Chatbot → send "What exercises help with muscle gain?" → verify a response is returned and it used RAG (check backend logs for retrieval).
4. Close browser, reopen at http://localhost:8501 → verify profile and chat history persist.
5. Attempt to visit Dashboard without a profile (clear session state manually) → verify redirect and warning message.

Polish:
6. Add a requirements.txt check at the top of backend/main.py startup: print a warning if any required env var is missing.
7. Ensure all st.spinner() calls are in place for any operation taking >0.5s.
8. Add st.set_page_config(page_title="FitAI", page_icon="💪", layout="wide") at the top of frontend/app.py.
9. Ensure no raw Python tracebacks are visible in the Streamlit UI — all errors surface as st.error() banners with user-friendly messages.
10. Write README.md with: project description, prerequisites, step-by-step setup instructions (pip install, .env setup, ingestion scripts, how to run backend and frontend), and a brief description of each page.
```

---

## Tips for Using These Prompts

- **Always start** by letting Claude Code read CLAUDE.md. Say: "Read CLAUDE.md first, then proceed."
- **One phase at a time.** Don't paste multiple prompts at once.
- **After each phase**, tick the corresponding tasks in TASKS.md before moving to the next prompt.
- **If a phase fails**, paste the error into Claude Code with: "Fix this error. Re-read CLAUDE.md if needed for context."
- **Phases 1 & 2 require** real PDF, GIF, and YouTube data in `data/knowledge/`. Add at least one sample file of each type before running Phase 2.
- **Phases 4+** require a valid `OPENAI_API_KEY` in `.env`.
