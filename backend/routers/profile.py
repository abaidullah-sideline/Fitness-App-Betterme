from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.database import get_connection
from backend.schemas.profile import ProfileCreate, ProfileResponse, ProfileUpdate

router = APIRouter(prefix="/api")

_PROFILE_COLS = (
    "user_id", "gender", "age_group", "bmi_category", "fitness_goal",
    "activity_level", "dietary_preference", "medical_conditions",
    "allergies_intolerances", "created_at", "updated_at",
)


def _row_to_response(row: tuple) -> ProfileResponse:
    data = dict(zip(_PROFILE_COLS, row))
    data["created_at"] = str(data["created_at"])
    data["updated_at"] = str(data["updated_at"])
    return ProfileResponse(**data)


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": True, "message": message}, status_code=status)


@router.post("/profile", response_model=ProfileResponse, status_code=201)
def create_profile(body: ProfileCreate):
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn = get_connection()
        with conn:
            conn.execute(
                """INSERT INTO users
                   (user_id, gender, age_group, bmi_category, fitness_goal,
                    activity_level, dietary_preference, medical_conditions,
                    allergies_intolerances, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    user_id, body.gender, body.age_group, body.bmi_category,
                    body.fitness_goal, body.activity_level, body.dietary_preference,
                    body.medical_conditions, body.allergies_intolerances, now, now,
                ),
            )
        conn.close()
    except Exception as exc:
        return _error(f"Failed to create profile: {exc}", 500)

    return ProfileResponse(
        user_id=user_id, created_at=now, updated_at=now, **body.model_dump()
    )


@router.get("/profile", response_model=ProfileResponse)
def get_profile(user_id: str = Query(...)):
    try:
        conn = get_connection()
        row = conn.execute(
            f"SELECT {', '.join(_PROFILE_COLS)} FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        conn.close()
    except Exception as exc:
        return _error(f"Database error: {exc}", 500)

    if row is None:
        return _error("Profile not found.", 404)

    return _row_to_response(row)


@router.put("/profile", response_model=ProfileResponse)
def update_profile(user_id: str = Query(...), body: ProfileUpdate = ...):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return _error("No fields provided for update.", 400)

    now = datetime.now(timezone.utc).isoformat()
    updates["updated_at"] = now

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values()) + [user_id]

    try:
        conn = get_connection()
        with conn:
            result = conn.execute(
                f"UPDATE users SET {set_clause} WHERE user_id = ?", values
            )
        if result.rowcount == 0:
            conn.close()
            return _error("Profile not found.", 404)
        row = conn.execute(
            f"SELECT {', '.join(_PROFILE_COLS)} FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        conn.close()
    except Exception as exc:
        return _error(f"Database error: {exc}", 500)

    return _row_to_response(row)
