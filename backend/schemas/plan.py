from __future__ import annotations

from pydantic import BaseModel


class DayPlan(BaseModel):
    day: str
    sr: int
    workout_plan: str
    breakfast: str
    lunch: str
    dinner: str
    est_calories_burned: int
    nutritional_facts: str


class PlanResponse(BaseModel):
    plan_id: str
    user_id: str
    days: list[DayPlan]
    created_at: str


class PlanEditRequest(BaseModel):
    user_id: str
    edit_command: str
    current_plan: list[DayPlan]


class PlanResetRequest(BaseModel):
    user_id: str
    plan_id: str


class CheckboxRequest(BaseModel):
    user_id: str
    plan_id: str
    day_of_week: str
    is_complete: bool


class DailyStats(BaseModel):
    day_of_week: str
    est_calories_burned: int
    fat_g: float
    carbs_g: float
    protein_g: float
    food_calories_kcal: int = 0
    nutritional_facts: str
