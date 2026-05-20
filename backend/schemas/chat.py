from __future__ import annotations

from pydantic import BaseModel


class ChatMessageRequest(BaseModel):
    user_id: str
    thread_id: str | None = None
    message: str


class ChatMessageResponse(BaseModel):
    thread_id: str
    response: str
    retrieved_sources: list[str]


class ThreadSummary(BaseModel):
    thread_id: str
    title: str
    updated_at: str


class MessageHistory(BaseModel):
    thread_id: str
    messages: list[dict]
