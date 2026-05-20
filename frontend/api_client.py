from __future__ import annotations

import os
import sys
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import requests
from backend.config import FASTAPI_BASE_URL

BASE = FASTAPI_BASE_URL.rstrip("/")


def _safe(fn):
    try:
        return fn()
    except requests.RequestException as exc:
        return {"error": True, "message": str(exc)}


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def create_profile(data: dict) -> dict:
    return _safe(lambda: requests.post(f"{BASE}/api/profile", json=data, timeout=15).json())


def get_profile(user_id: str) -> dict:
    return _safe(lambda: requests.get(f"{BASE}/api/profile", params={"user_id": user_id}, timeout=10).json())


def update_profile(user_id: str, data: dict) -> dict:
    return _safe(lambda: requests.put(f"{BASE}/api/profile/{user_id}", json=data, timeout=15).json())


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def get_plan(user_id: str) -> dict:
    return _safe(lambda: requests.get(f"{BASE}/api/plan", params={"user_id": user_id}, timeout=60).json())


def edit_plan(user_id: str, command: str, current_plan: list) -> dict:
    payload = {"user_id": user_id, "edit_command": command, "current_plan": current_plan}
    return _safe(lambda: requests.post(f"{BASE}/api/plan/edit", json=payload, timeout=60).json())


def toggle_checkbox(user_id: str, plan_id: str, day: str, is_complete: bool) -> dict:
    payload = {"user_id": user_id, "plan_id": plan_id, "day_of_week": day, "is_complete": is_complete}
    return _safe(lambda: requests.post(f"{BASE}/api/plan/checkbox", json=payload, timeout=10).json())


def reset_plan(user_id: str, plan_id: str) -> dict:
    payload = {"user_id": user_id, "plan_id": plan_id}
    return _safe(lambda: requests.post(f"{BASE}/api/plan/reset", json=payload, timeout=10).json())


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

def get_chats(user_id: str) -> list:
    result = _safe(lambda: requests.get(f"{BASE}/api/chats", params={"user_id": user_id}, timeout=10).json())
    if isinstance(result, list):
        return result
    return []


def send_message(user_id: str, thread_id: str | None, message: str) -> dict:
    payload = {"user_id": user_id, "thread_id": thread_id, "message": message}
    return _safe(lambda: requests.post(f"{BASE}/api/chat", json=payload, timeout=60).json())


def get_thread(thread_id: str) -> dict:
    return _safe(lambda: requests.get(f"{BASE}/api/chat/{thread_id}", timeout=10).json())


def delete_thread(thread_id: str) -> bool:
    result = _safe(lambda: requests.delete(f"{BASE}/api/chat/{thread_id}", timeout=10).json())
    return bool(result.get("deleted")) if isinstance(result, dict) else False
