"""LangGraph chatbot — router, RAG retrieval, generation, memory update."""

from __future__ import annotations

import logging
import pathlib
import re
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Annotated, Literal, TypedDict

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from backend.config import CHROMA_PATH, DB_PATH, OPENAI_API_KEY
from backend.database import get_connection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    messages: Annotated[list, add_messages]
    user_profile: dict
    thread_id: str
    retrieved_docs: list[str]
    memory_summary: str
    turn_count: int
    is_fitness_topic: bool   # internal routing flag


# ---------------------------------------------------------------------------
# LLM factory (lazy — does not call OpenAI at import time)
# ---------------------------------------------------------------------------

def _llm(temperature: float = 0.7) -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4o-mini",
        openai_api_key=OPENAI_API_KEY,
        temperature=temperature,
    )


# ---------------------------------------------------------------------------
# Fitness topic heuristic (keyword-based, zero API calls)
# ---------------------------------------------------------------------------

_FITNESS_KEYWORDS = {
    "workout", "exercise", "fitness", "gym", "training", "muscle", "strength",
    "cardio", "hiit", "yoga", "run", "running", "jog", "weight", "weights",
    "calories", "calorie", "protein", "carbs", "fat", "diet", "nutrition",
    "meal", "food", "eat", "eating", "supplement", "recovery", "stretch",
    "squat", "deadlift", "bench", "push", "pull", "reps", "sets", "bmi",
    "endurance", "stamina", "health", "healthy", "sleep", "hydration",
}


def _classify_fitness(message: str) -> bool:
    words = set(re.findall(r"\b\w+\b", message.lower()))
    return bool(words & _FITNESS_KEYWORDS)


# ---------------------------------------------------------------------------
# Node: router
# ---------------------------------------------------------------------------

def router_node(state: GraphState) -> dict:
    last = state["messages"][-1]
    content = last.content if hasattr(last, "content") else str(last)
    # Clear docs from the previous turn so the final state reflects this turn's retrieval
    return {"is_fitness_topic": _classify_fitness(content), "retrieved_docs": []}


# ---------------------------------------------------------------------------
# Node: retrieve
# ---------------------------------------------------------------------------

def retrieve_node(state: GraphState) -> dict:
    last = state["messages"][-1]
    query = last.content if hasattr(last, "content") else str(last)
    docs: list[str] = []

    # 1. Chroma chatbot_kb — semantic chunks from PDFs
    try:
        from langchain_chroma import Chroma
        from langchain_openai import OpenAIEmbeddings

        persist_dir = str(PROJECT_ROOT / CHROMA_PATH / "chatbot_kb")
        db = Chroma(
            collection_name="chatbot_kb",
            embedding_function=OpenAIEmbeddings(
                openai_api_key=OPENAI_API_KEY,
                model="text-embedding-3-small",
            ),
            persist_directory=persist_dir,
        )
        for doc in db.similarity_search(query, k=3):
            docs.append(doc.page_content)
    except Exception as exc:
        logger.warning("chatbot_kb retrieval failed: %s", exc)

    # 2. GIF metadata — keyword match on exercise name
    keywords = [w for w in re.findall(r"\b\w{3,}\b", query.lower())][:6]
    try:
        conn = get_connection()
        seen_gifs: set[str] = set()
        for kw in keywords:
            for exercise_name, muscle_group, difficulty, file_path in conn.execute(
                "SELECT exercise_name, muscle_group, difficulty, file_path "
                "FROM gif_metadata WHERE LOWER(exercise_name) LIKE ?",
                (f"%{kw}%",),
            ).fetchall():
                if file_path not in seen_gifs:
                    docs.append(
                        f"[GIF] {exercise_name} — {muscle_group}, {difficulty} | {file_path}"
                    )
                    seen_gifs.add(file_path)
        conn.close()
    except Exception as exc:
        logger.warning("gif_metadata retrieval failed: %s", exc)

    # 3. YouTube resources — keyword match on tags / title
    try:
        conn = get_connection()
        seen: set[str] = set()
        for kw in keywords:
            for title, url, tags in conn.execute(
                "SELECT title, url, tags FROM youtube_resources "
                "WHERE LOWER(tags) LIKE ? OR LOWER(title) LIKE ?",
                (f"%{kw}%", f"%{kw}%"),
            ).fetchall():
                if url not in seen:
                    docs.append(f"[YouTube] {title} | {url} | tags: {tags}")
                    seen.add(url)
        conn.close()
    except Exception as exc:
        logger.warning("youtube_resources retrieval failed: %s", exc)

    return {"retrieved_docs": docs}


# ---------------------------------------------------------------------------
# Node: generate
# ---------------------------------------------------------------------------

def generate_node(state: GraphState) -> dict:
    profile = state.get("user_profile") or {}
    memory = state.get("memory_summary") or ""
    docs = state.get("retrieved_docs") or []

    profile_summary = (
        f"{profile.get('gender', 'User')}, age group {profile.get('age_group', 'unknown')}, "
        f"{profile.get('bmi_category', 'unknown')} BMI. "
        f"Goal: {profile.get('fitness_goal', 'general fitness')}. "
        f"Activity: {profile.get('activity_level', 'moderate')}. "
        f"Diet: {profile.get('dietary_preference', 'no preference')}. "
        f"Medical: {profile.get('medical_conditions', 'none')}."
    )

    system_parts = [
        "You are FitAI, a knowledgeable, concise, and encouraging fitness and nutrition assistant.",
        f"User profile: {profile_summary}",
    ]
    if memory:
        system_parts.append(f"Memory from prior sessions:\n{memory}")
    if docs:
        context = "\n".join(f"  • {d}" for d in docs)
        system_parts.append(f"Relevant resources for this response:\n{context}")

    llm = _llm(temperature=0.7)
    response = llm.invoke([SystemMessage(content="\n\n".join(system_parts))] + list(state["messages"]))

    return {
        "messages": [response],
        "turn_count": state.get("turn_count", 0) + 1,
    }


# ---------------------------------------------------------------------------
# Node: update_memory
# ---------------------------------------------------------------------------

def update_memory_node(state: GraphState) -> dict:
    if state.get("turn_count", 0) % 5 != 0:
        return {}

    recent_msgs = list(state["messages"])[-10:]
    history_text = "\n".join(
        f"{type(m).__name__}: {m.content}"
        for m in recent_msgs
        if hasattr(m, "content")
    )

    try:
        llm = _llm(temperature=0.0)
        summary = llm.invoke([
            SystemMessage(
                content=(
                    "Summarise the following fitness coaching conversation in 3-5 sentences. "
                    "Focus on the user's goals, any advice given, exercises or meals discussed, "
                    "and important personal details to remember."
                )
            ),
            HumanMessage(content=history_text),
        ]).content
    except Exception as exc:
        logger.error("Memory summarisation LLM call failed: %s", exc)
        return {}

    user_id = (state.get("user_profile") or {}).get("user_id", "")
    thread_id = state.get("thread_id", "")
    if user_id and thread_id:
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn = get_connection()
            existing = conn.execute(
                "SELECT id FROM memory_summaries WHERE user_id = ? AND thread_id = ?",
                (user_id, thread_id),
            ).fetchone()
            with conn:
                if existing:
                    conn.execute(
                        "UPDATE memory_summaries SET summary_text = ?, updated_at = ? WHERE id = ?",
                        (summary, now, existing[0]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO memory_summaries (user_id, thread_id, summary_text, updated_at) "
                        "VALUES (?,?,?,?)",
                        (user_id, thread_id, summary, now),
                    )
            conn.close()
        except Exception as exc:
            logger.error("Failed to persist memory summary: %s", exc)

    return {"memory_summary": summary}


# ---------------------------------------------------------------------------
# Routing function
# ---------------------------------------------------------------------------

def _route_after_router(state: GraphState) -> Literal["retrieve", "generate"]:
    return "retrieve" if state.get("is_fitness_topic", False) else "generate"


# ---------------------------------------------------------------------------
# Graph (module-level singleton, lazy-initialised)
# ---------------------------------------------------------------------------

_graph = None
_ckpt_conn: sqlite3.Connection | None = None


def _get_graph():
    global _graph, _ckpt_conn
    if _graph is None:
        # check_same_thread=False required — LangGraph runs nodes in a ThreadPoolExecutor
        _ckpt_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        checkpointer = SqliteSaver(_ckpt_conn)

        builder = StateGraph(GraphState)
        builder.add_node("router", router_node)
        builder.add_node("retrieve", retrieve_node)
        builder.add_node("generate", generate_node)
        builder.add_node("update_memory", update_memory_node)

        builder.set_entry_point("router")
        builder.add_conditional_edges(
            "router",
            _route_after_router,
            {"retrieve": "retrieve", "generate": "generate"},
        )
        builder.add_edge("retrieve", "generate")
        builder.add_edge("generate", "update_memory")
        builder.add_edge("update_memory", END)

        _graph = builder.compile(checkpointer=checkpointer)
    return _graph


# ---------------------------------------------------------------------------
# Private helpers for run_chat
# ---------------------------------------------------------------------------

def _load_memory_summary(user_id: str, thread_id: str) -> str:
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT summary_text FROM memory_summaries "
            "WHERE user_id = ? AND thread_id = ? ORDER BY updated_at DESC LIMIT 1",
            (user_id, thread_id),
        ).fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception:
        return ""


def _load_user_profile(user_id: str) -> dict:
    _COLS = (
        "user_id", "gender", "age_group", "bmi_category", "fitness_goal",
        "activity_level", "dietary_preference", "medical_conditions", "allergies_intolerances",
    )
    try:
        conn = get_connection()
        row = conn.execute(
            f"SELECT {', '.join(_COLS)} FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.close()
        return dict(zip(_COLS, row)) if row else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Public: run_chat
# ---------------------------------------------------------------------------

def run_chat(user_id: str, thread_id: str, message: str) -> tuple[str, list[str]]:
    """
    Process one chat turn. Returns (assistant_reply, retrieved_sources).
    On first call for a thread: initialises state from SQLite.
    On subsequent calls: LangGraph restores state from the checkpoint.
    """
    graph = _get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    checkpoint = graph.checkpointer.get(config)
    if checkpoint is None:
        input_state: dict = {
            "messages": [HumanMessage(content=message)],
            "user_profile": _load_user_profile(user_id),
            "thread_id": thread_id,
            "retrieved_docs": [],
            "memory_summary": _load_memory_summary(user_id, thread_id),
            "turn_count": 0,
            "is_fitness_topic": False,
        }
    else:
        input_state = {"messages": [HumanMessage(content=message)]}

    result = graph.invoke(input_state, config=config)

    reply = ""
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage):
            reply = msg.content
            break

    sources: list[str] = result.get("retrieved_docs") or []
    return reply, sources
