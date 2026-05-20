from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.database import get_connection
from backend.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    MessageHistory,
    ThreadSummary,
)
from backend.services.chatbot import _get_graph, run_chat

router = APIRouter(prefix="/api")

_CKPT_TABLES = ("checkpoints", "writes")


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": True, "message": message}, status_code=status)


# ---------------------------------------------------------------------------
# GET /api/chats
# ---------------------------------------------------------------------------

@router.get("/chats", response_model=list[ThreadSummary])
def list_threads(user_id: str = Query(...)):
    conn = get_connection()
    rows = conn.execute(
        "SELECT thread_id, title, updated_at FROM chat_threads "
        "WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [ThreadSummary(thread_id=r[0], title=r[1], updated_at=str(r[2])) for r in rows]


# ---------------------------------------------------------------------------
# POST /api/chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatMessageResponse)
def send_message(body: ChatMessageRequest):
    thread_id = body.thread_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()

    # Create thread row if new
    existing = conn.execute(
        "SELECT thread_id FROM chat_threads WHERE thread_id = ?", (thread_id,)
    ).fetchone()

    title = body.message[:40]
    with conn:
        if not existing:
            conn.execute(
                "INSERT INTO chat_threads (thread_id, user_id, title, created_at, updated_at) "
                "VALUES (?,?,?,?,?)",
                (thread_id, body.user_id, title, now, now),
            )
        else:
            conn.execute(
                "UPDATE chat_threads SET updated_at = ? WHERE thread_id = ?",
                (now, thread_id),
            )
    conn.close()

    try:
        reply, sources = run_chat(body.user_id, thread_id, body.message)
    except Exception as exc:
        return _error(f"Chat engine error: {exc}", 500)

    # Update updated_at after the (potentially slow) LLM call
    conn2 = get_connection()
    with conn2:
        conn2.execute(
            "UPDATE chat_threads SET updated_at = ? WHERE thread_id = ?",
            (datetime.now(timezone.utc).isoformat(), thread_id),
        )
    conn2.close()

    return ChatMessageResponse(
        thread_id=thread_id,
        response=reply,
        retrieved_sources=sources,
    )


# ---------------------------------------------------------------------------
# GET /api/chat/{thread_id}
# ---------------------------------------------------------------------------

@router.get("/chat/{thread_id}", response_model=MessageHistory)
def get_thread(thread_id: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT thread_id FROM chat_threads WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    conn.close()

    if row is None:
        return _error("Thread not found.", 404)

    graph = _get_graph()
    checkpoint = graph.checkpointer.get({"configurable": {"thread_id": thread_id}})

    messages: list[dict] = []
    if checkpoint:
        raw_msgs = checkpoint["channel_values"].get("messages", [])
        for m in raw_msgs:
            role = getattr(m, "type", "unknown")
            # LangChain type values: "human" → "user", "ai" → "assistant"
            role = {"human": "user", "ai": "assistant"}.get(role, role)
            messages.append({"role": role, "content": getattr(m, "content", str(m))})

    return MessageHistory(thread_id=thread_id, messages=messages)


# ---------------------------------------------------------------------------
# DELETE /api/chat/{thread_id}
# ---------------------------------------------------------------------------

@router.delete("/chat/{thread_id}")
def delete_thread(thread_id: str):
    conn = get_connection()

    row = conn.execute(
        "SELECT thread_id FROM chat_threads WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return _error("Thread not found.", 404)

    with conn:
        conn.execute("DELETE FROM chat_threads WHERE thread_id = ?", (thread_id,))
        conn.execute("DELETE FROM memory_summaries WHERE thread_id = ?", (thread_id,))
        conn.execute("DELETE FROM chat_checkpoints WHERE thread_id = ?", (thread_id,))
        # SqliteSaver checkpoint tables
        for table in _CKPT_TABLES:
            try:
                conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,))
            except Exception:
                pass
    conn.close()

    return {"deleted": True, "thread_id": thread_id}
