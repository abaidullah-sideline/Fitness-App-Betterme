from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.database import get_connection
from backend.schemas.plan import (
    CheckboxRequest,
    DailyStats,
    DayPlan,
    PlanEditRequest,
    PlanResetRequest,
    PlanResponse,
)
from backend.services.plan_editor import edit_plan
from backend.services.recommender import get_recommendations, parse_plan_to_days

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_USER_COLS = (
    "user_id", "gender", "age_group", "bmi_category", "fitness_goal",
    "activity_level", "dietary_preference", "medical_conditions",
    "allergies_intolerances", "created_at", "updated_at",
)
_PLAN_COLS = (
    "plan_id", "user_id", "plan_json", "edit_history_json",
    "created_at", "original_plan_json",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": True, "message": message}, status_code=status)


def _row_to_plan_response(plan_row: dict, user_id: str) -> PlanResponse:
    days = [DayPlan(**d) for d in json.loads(plan_row["plan_json"])]
    return PlanResponse(
        plan_id=plan_row["plan_id"],
        user_id=user_id,
        days=days,
        created_at=str(plan_row["created_at"]),
    )


def _fetch_user(conn, user_id: str) -> dict | None:
    row = conn.execute(
        f"SELECT {', '.join(_USER_COLS)} FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    return dict(zip(_USER_COLS, row)) if row else None


def _fetch_latest_plan(conn, user_id: str) -> dict | None:
    row = conn.execute(
        f"SELECT {', '.join(_PLAN_COLS)} FROM plans WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    return dict(zip(_PLAN_COLS, row)) if row else None


def _parse_nutrition(nutritional_facts: str) -> dict:
    """Extract macro grams and total food calories from a nutritional_facts string.

    Handles formats like:
      {Calories: 2800 kcal, Protein: 150g, Carbs: 320g, Fats: 85g}
    """
    def _g(label: str) -> float:
        m = re.search(rf"{label}\s*:\s*(\d+(?:\.\d+)?)\s*g", nutritional_facts, re.IGNORECASE)
        return float(m.group(1)) if m else 0.0

    def _kcal(label: str) -> int:
        m = re.search(rf"{label}\s*:\s*(\d+)\s*kcal", nutritional_facts, re.IGNORECASE)
        return int(m.group(1)) if m else 0

    return {
        "fat_g": _g(r"Fats?"),
        "carbs_g": _g(r"Carbs?"),
        "protein_g": _g("Protein"),
        "food_calories_kcal": _kcal("Calories"),
    }


# ---------------------------------------------------------------------------
# GET /api/plan
# ---------------------------------------------------------------------------

@router.get("/plan", response_model=PlanResponse)
def get_plan(user_id: str = Query(...)):
    conn = get_connection()

    user = _fetch_user(conn, user_id)
    if user is None:
        conn.close()
        return _error("User not found.", 404)

    # Return cached plan if profile hasn't been updated since it was generated
    plan_row = _fetch_latest_plan(conn, user_id)
    if plan_row and str(user["updated_at"]) <= str(plan_row["created_at"]):
        conn.close()
        return _row_to_plan_response(plan_row, user_id)

    # Build profile dict for recommender
    profile = {k: user[k] for k in (
        "gender", "age_group", "bmi_category", "fitness_goal",
        "activity_level", "dietary_preference", "medical_conditions",
        "allergies_intolerances",
    )}

    try:
        recommendations = get_recommendations(profile)
    except Exception as exc:
        conn.close()
        logger.error("Recommendation engine error: %s", exc)
        return _error(
            f"Could not generate plan. Ensure plans_kb is populated by running "
            f"ingest_plans.py with a valid OPENAI_API_KEY. Detail: {exc}",
            500,
        )

    if not recommendations:
        conn.close()
        return _error("No matching plans found for this profile.", 404)

    days = parse_plan_to_days(recommendations[0])
    plan_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    plan_json_str = json.dumps(days)

    with conn:
        conn.execute(
            """INSERT INTO plans
               (plan_id, user_id, plan_json, original_plan_json, edit_history_json, created_at)
               VALUES (?,?,?,?,?,?)""",
            (plan_id, user_id, plan_json_str, plan_json_str, json.dumps([]), now),
        )
    conn.close()

    return PlanResponse(plan_id=plan_id, user_id=user_id,
                        days=[DayPlan(**d) for d in days], created_at=now)


# ---------------------------------------------------------------------------
# POST /api/plan/edit
# ---------------------------------------------------------------------------

@router.post("/plan/edit", response_model=PlanResponse)
def edit_plan_endpoint(body: PlanEditRequest):
    conn = get_connection()

    plan_row = _fetch_latest_plan(conn, body.user_id)
    if plan_row is None:
        conn.close()
        return _error("No plan found for this user.", 404)

    current_plan = [d.model_dump() for d in body.current_plan]
    updated_plan = edit_plan(current_plan, body.edit_command)

    history: list = json.loads(plan_row["edit_history_json"] or "[]")
    history.append(body.edit_command)
    history = history[-10:]

    plan_json_str = json.dumps(updated_plan)
    with conn:
        conn.execute(
            "UPDATE plans SET plan_json = ?, edit_history_json = ? WHERE plan_id = ?",
            (plan_json_str, json.dumps(history), plan_row["plan_id"]),
        )
    conn.close()

    return PlanResponse(
        plan_id=plan_row["plan_id"],
        user_id=body.user_id,
        days=[DayPlan(**d) for d in updated_plan],
        created_at=str(plan_row["created_at"]),
    )


# ---------------------------------------------------------------------------
# POST /api/plan/checkbox
# ---------------------------------------------------------------------------

@router.post("/plan/checkbox", response_model=DailyStats)
def toggle_checkbox(body: CheckboxRequest):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()

    # Upsert day_logs
    existing = conn.execute(
        "SELECT log_id FROM day_logs WHERE user_id = ? AND plan_id = ? AND day_of_week = ?",
        (body.user_id, body.plan_id, body.day_of_week),
    ).fetchone()

    with conn:
        if existing:
            conn.execute(
                "UPDATE day_logs SET is_complete = ?, completed_at = ? WHERE log_id = ?",
                (int(body.is_complete), now if body.is_complete else None, existing[0]),
            )
        else:
            conn.execute(
                "INSERT INTO day_logs (log_id, user_id, plan_id, day_of_week, is_complete, completed_at) "
                "VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), body.user_id, body.plan_id, body.day_of_week,
                 int(body.is_complete), now if body.is_complete else None),
            )

    # Fetch plan and find the matching day
    plan_row = conn.execute(
        "SELECT plan_json FROM plans WHERE plan_id = ?", (body.plan_id,)
    ).fetchone()
    conn.close()

    if plan_row is None:
        return JSONResponse({"error": True, "message": "Plan not found."}, status_code=404)

    days: list[dict] = json.loads(plan_row[0])
    day_data = next(
        (d for d in days if d["day"].lower() == body.day_of_week.lower()), None
    )
    if day_data is None:
        return JSONResponse({"error": True, "message": f"Day '{body.day_of_week}' not found in plan."}, status_code=404)

    nutrition = _parse_nutrition(day_data.get("nutritional_facts", ""))
    return DailyStats(
        day_of_week=body.day_of_week,
        est_calories_burned=int(day_data.get("est_calories_burned", 0)),
        nutritional_facts=day_data.get("nutritional_facts", ""),
        **nutrition,
    )


# ---------------------------------------------------------------------------
# POST /api/plan/reset
# ---------------------------------------------------------------------------

@router.post("/plan/reset", response_model=PlanResponse)
def reset_plan(body: PlanResetRequest):
    conn = get_connection()

    plan_row = conn.execute(
        f"SELECT {', '.join(_PLAN_COLS)} FROM plans WHERE plan_id = ? AND user_id = ?",
        (body.plan_id, body.user_id),
    ).fetchone()

    if plan_row is None:
        conn.close()
        return _error("Plan not found.", 404)

    plan = dict(zip(_PLAN_COLS, plan_row))
    original = plan["original_plan_json"] or plan["plan_json"]

    with conn:
        conn.execute(
            "UPDATE plans SET plan_json = ?, edit_history_json = ? WHERE plan_id = ?",
            (original, json.dumps([]), body.plan_id),
        )
    conn.close()

    return PlanResponse(
        plan_id=plan["plan_id"],
        user_id=body.user_id,
        days=[DayPlan(**d) for d in json.loads(original)],
        created_at=str(plan["created_at"]),
    )
