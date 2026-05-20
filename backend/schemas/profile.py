from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class ProfileCreate(BaseModel):
    gender: str
    age_group: str
    bmi_category: str
    fitness_goal: str
    activity_level: str
    dietary_preference: str
    medical_conditions: str = "None"
    allergies_intolerances: str = "None"


class ProfileUpdate(BaseModel):
    gender: Optional[str] = None
    age_group: Optional[str] = None
    bmi_category: Optional[str] = None
    fitness_goal: Optional[str] = None
    activity_level: Optional[str] = None
    dietary_preference: Optional[str] = None
    medical_conditions: Optional[str] = None
    allergies_intolerances: Optional[str] = None


class ProfileResponse(ProfileCreate):
    user_id: str
    created_at: str
    updated_at: str
