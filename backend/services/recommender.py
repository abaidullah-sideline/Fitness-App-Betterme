"""Semantic recommendation engine — Chroma vector search + pandas hard filtering."""

from __future__ import annotations

import logging
import pathlib
import re
import sys

import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import CHROMA_PATH, OPENAI_API_KEY  # noqa: E402

logger = logging.getLogger(__name__)

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Abbreviated day prefixes that may appear in schedule text
_DAY_PREFIX_RE = re.compile(
    r"^(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)\s*[:\-–]\s*",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Public: build_user_query
# ---------------------------------------------------------------------------

def build_user_query(profile: dict) -> str:
    """Convert a profile dict into a natural-language sentence for vector search."""
    gender = profile.get("gender", "person")
    age = profile.get("age_group", "unknown age")
    bmi = profile.get("bmi_category", "unknown BMI")
    goal = profile.get("fitness_goal", "general fitness")
    activity = profile.get("activity_level", "moderate")
    diet = profile.get("dietary_preference", "No Preference")
    conditions = profile.get("medical_conditions", "None")
    allergies = profile.get("allergies_intolerances", "None")

    diet_phrase = (
        "no dietary restrictions"
        if diet.lower() in ("no preference", "any", "all", "none")
        else f"a {diet.lower()} diet"
    )
    conditions_phrase = (
        "no known medical conditions"
        if conditions.lower() in ("none", "n/a", "")
        else f"medical conditions: {conditions}"
    )
    allergies_phrase = (
        "no allergies"
        if allergies.lower() in ("none", "n/a", "")
        else f"allergies or intolerances: {allergies}"
    )

    return (
        f"A {age} year old {gender.lower()} with {bmi} BMI looking to {goal.lower()}. "
        f"{activity} activity level with {diet_phrase}. "
        f"{conditions_phrase.capitalize()} and {allergies_phrase}."
    )


# ---------------------------------------------------------------------------
# Public: get_recommendations
# ---------------------------------------------------------------------------

def get_recommendations(profile: dict) -> list[dict]:
    """
    Return top-3 plan dicts ranked by semantic similarity + hard filters.
    Each dict has: Plan_ID, Exercise_Schedule, Meal_Plan,
                   Nutritional_Facts, Est_Calories_Burned.
    """
    from langchain_chroma import Chroma
    from langchain_openai import OpenAIEmbeddings

    persist_dir = str(PROJECT_ROOT / CHROMA_PATH / "plans_kb")
    embeddings = OpenAIEmbeddings(
        openai_api_key=OPENAI_API_KEY,
        model="text-embedding-3-small",
    )
    db = Chroma(
        collection_name="plans_kb",
        embedding_function=embeddings,
        persist_directory=persist_dir,
    )

    user_query = build_user_query(profile)
    docs = db.similarity_search(user_query, k=20)

    # Extract Plan_IDs from Semantic_Description content
    plan_ids: list[str] = []
    for doc in docs:
        first_line = doc.page_content.split("\n")[0].strip()
        # Plan_ID is the first token before a colon or whitespace
        match = re.match(r"^(\S+?)[\s:]", first_line)
        if match:
            plan_ids.append(match.group(1))

    if not plan_ids:
        return []

    # Load dataset and filter to retrieved plan IDs
    dataset_path = PROJECT_ROOT / "data" / "dataset.csv"
    df = pd.read_csv(dataset_path)
    df = df[df["Plan_ID"].isin(plan_ids)].copy()

    # Hard filters — skip if the user chose "Any" / "All".
    # When filtering, also keep dataset rows whose column value is "Any"
    # (they are valid for every user profile).
    _SKIP = {"any", "all"}
    filter_map = {
        "Gender": profile.get("gender", ""),
        "Fitness_Goal": profile.get("fitness_goal", ""),
        "Dietary_Preference": profile.get("dietary_preference", ""),
    }
    for col, value in filter_map.items():
        if value.lower() not in _SKIP and value:
            df = df[
                (df[col].str.lower() == value.lower()) |
                (df[col].str.lower() == "any")
            ]

    # Preserve similarity ranking order
    id_rank = {pid: i for i, pid in enumerate(plan_ids)}
    df["_rank"] = df["Plan_ID"].map(id_rank)
    df = df.sort_values("_rank").drop(columns="_rank")

    top3 = df.head(3)
    return top3[
        ["Plan_ID", "Exercise_Schedule", "Meal_Plan", "Nutritional_Facts", "Est_Calories_Burned"]
    ].to_dict(orient="records")


# ---------------------------------------------------------------------------
# Public: parse_plan_to_days
# ---------------------------------------------------------------------------

def parse_plan_to_days(plan: dict) -> list[dict]:
    """
    Parse Exercise_Schedule and Meal_Plan into a 7-element day list.
    Each element: {day, sr, workout_plan, breakfast, lunch, dinner,
                   est_calories_burned, nutritional_facts}
    """
    workouts = _parse_exercise_schedule(plan.get("Exercise_Schedule", ""))
    meals = _parse_meal_plan(plan.get("Meal_Plan", ""))
    calories = plan.get("Est_Calories_Burned", 0)
    nutrition = plan.get("Nutritional_Facts", "")

    return [
        {
            "day": _DAYS[i],
            "sr": i + 1,
            "workout_plan": workouts[i],
            "breakfast": meals[i][0],
            "lunch": meals[i][1],
            "dinner": meals[i][2],
            "est_calories_burned": calories,
            "nutritional_facts": nutrition,
        }
        for i in range(7)
    ]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _parse_exercise_schedule(schedule: str) -> list[str]:
    """Split a schedule string into exactly 7 workout strings."""
    parts = [p.strip() for p in schedule.split(";") if p.strip()]

    workouts: list[str] = []
    for part in parts:
        # Strip leading day prefix ("Mon: ", "Monday - ", etc.)
        workout = _DAY_PREFIX_RE.sub("", part).strip()
        workouts.append(workout or "Rest")

    return _normalise_to_seven(workouts, "Rest", "exercise schedule")


def _parse_meal_plan(meal_plan: str) -> list[tuple[str, str, str]]:
    """
    Return 7 (breakfast, lunch, dinner) tuples.

    Strategy:
    1. If the text contains 7 day-level groups, parse each group for B/L/D.
    2. Otherwise treat the text as a single repeated daily template.
    """
    # Try per-day split (groups separated by ";")
    groups = [g.strip() for g in meal_plan.split(";") if g.strip()]

    # Heuristic: if 7 groups and most start with a day prefix, parse per-day
    day_groups = [g for g in groups if _DAY_PREFIX_RE.match(g)]
    if len(day_groups) >= 6:
        meals = [_extract_bld(g) for g in _normalise_to_seven(day_groups, "", "meal plan")]
        return meals

    # Single template — parse once, repeat for all 7 days
    bld = _extract_bld(meal_plan)
    return [bld] * 7


def _extract_bld(text: str) -> tuple[str, str, str]:
    """Extract breakfast, lunch, dinner from a text fragment."""
    # Remove leading day prefix if present
    text = _DAY_PREFIX_RE.sub("", text).strip()

    # Split on commas or semicolons to get meal tokens
    tokens = [t.strip() for t in re.split(r"[;,]", text) if t.strip()]

    breakfast = lunch = dinner = ""
    for token in tokens:
        lower = token.lower()
        if re.match(r"^breakfast\s*:", lower):
            breakfast = re.split(r":", token, 1)[1].strip()
        elif re.match(r"^lunch\s*:", lower):
            lunch = re.split(r":", token, 1)[1].strip()
        elif re.match(r"^dinner\s*:", lower):
            dinner = re.split(r":", token, 1)[1].strip()

    # If no labelled meals found, distribute tokens positionally
    if not (breakfast or lunch or dinner):
        if tokens:
            breakfast = tokens[0] if len(tokens) > 0 else ""
            lunch = tokens[1] if len(tokens) > 1 else ""
            dinner = tokens[2] if len(tokens) > 2 else ""

    return (breakfast, lunch, dinner)


def _normalise_to_seven(items: list[str], default: str, label: str) -> list[str]:
    """Pad or truncate a list to exactly 7 items, logging a warning if adjusted."""
    n = len(items)
    if n == 7:
        return items
    if n < 7:
        logger.warning(
            "Could not split %s into 7 parts (got %d); padding with %r.", label, n, default
        )
        return items + [default] * (7 - n)
    logger.warning(
        "Could not split %s into 7 parts (got %d); truncating.", label, n
    )
    return items[:7]
