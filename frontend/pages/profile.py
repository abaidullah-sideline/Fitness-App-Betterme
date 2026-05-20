from __future__ import annotations

import sys
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from frontend.api_client import create_profile, get_profile, update_profile

# ---------------------------------------------------------------------------
# Field options
# ---------------------------------------------------------------------------

_SENTINEL = "-- Select --"

_AGE_GROUPS = [_SENTINEL, "18-30", "31-45", "46-60", "61+"]
_BMI_CATS = [_SENTINEL, "Underweight", "Normal", "Overweight", "Obese"]
_FITNESS_GOALS = [_SENTINEL, "Weight Loss", "Muscle Gain", "Improve Endurance", "Maintain Fitness"]
_ACTIVITY_LEVELS = [_SENTINEL, "Low", "Moderate", "High"]
_DIETARY_PREFS = [_SENTINEL, "Omnivore", "Vegetarian", "Vegan", "No Preference"]
_GENDERS = ["Male", "Female", "Non-binary", "Prefer not to say"]

_REQUIRED_SELECTS = {
    "age_group": ("Age Group", _AGE_GROUPS),
    "bmi_category": ("BMI Category", _BMI_CATS),
    "fitness_goal": ("Fitness Goal", _FITNESS_GOALS),
    "activity_level": ("Activity Level", _ACTIVITY_LEVELS),
    "dietary_preference": ("Dietary Preference", _DIETARY_PREFS),
}

_FIELD_LABELS = {
    "gender": "Gender",
    "age_group": "Age Group",
    "bmi_category": "BMI Category",
    "fitness_goal": "Fitness Goal",
    "activity_level": "Activity Level",
    "dietary_preference": "Dietary Preference",
    "medical_conditions": "Medical Conditions",
    "allergies_intolerances": "Allergies / Intolerances",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_index(options: list, value: str) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0


def _render_form(prefill: dict | None = None) -> None:
    """Render the create/edit form. prefill contains existing values when editing."""
    is_edit = prefill is not None
    title = "Edit your profile" if is_edit else "Set up your profile"

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown(f"### {title}")
        st.markdown("---")

        with st.form("profile_form", clear_on_submit=False):
            gender = st.radio(
                "Gender *",
                _GENDERS,
                index=_safe_index(_GENDERS, prefill.get("gender", "Male") if prefill else "Male"),
                horizontal=True,
            )

            age_group = st.selectbox(
                "Age Group *",
                _AGE_GROUPS,
                index=_safe_index(_AGE_GROUPS, prefill.get("age_group", _SENTINEL) if prefill else 0),
            )

            bmi_category = st.selectbox(
                "BMI Category *",
                _BMI_CATS,
                index=_safe_index(_BMI_CATS, prefill.get("bmi_category", _SENTINEL) if prefill else 0),
            )

            fitness_goal = st.selectbox(
                "Fitness Goal *",
                _FITNESS_GOALS,
                index=_safe_index(_FITNESS_GOALS, prefill.get("fitness_goal", _SENTINEL) if prefill else 0),
            )

            activity_level = st.selectbox(
                "Activity Level *",
                _ACTIVITY_LEVELS,
                index=_safe_index(_ACTIVITY_LEVELS, prefill.get("activity_level", _SENTINEL) if prefill else 0),
            )

            dietary_preference = st.selectbox(
                "Dietary Preference *",
                _DIETARY_PREFS,
                index=_safe_index(_DIETARY_PREFS, prefill.get("dietary_preference", _SENTINEL) if prefill else 0),
            )

            medical_conditions = st.text_area(
                "Medical Conditions",
                value=prefill.get("medical_conditions", "") if prefill else "",
                placeholder="e.g. Diabetes, Hypertension — leave blank if none",
                height=80,
            )

            allergies_intolerances = st.text_area(
                "Allergies / Intolerances",
                value=prefill.get("allergies_intolerances", "") if prefill else "",
                placeholder="e.g. Lactose, Gluten — leave blank if none",
                height=80,
            )

            btn_label = "Save changes" if is_edit else "Create profile"
            submitted = st.form_submit_button(btn_label, use_container_width=True, type="primary")

        if submitted:
            # Validate required selects
            errors: list[str] = []
            selections = {
                "age_group": age_group,
                "bmi_category": bmi_category,
                "fitness_goal": fitness_goal,
                "activity_level": activity_level,
                "dietary_preference": dietary_preference,
            }
            for field, value in selections.items():
                if value == _SENTINEL:
                    errors.append(f"{_FIELD_LABELS[field]} is required.")

            if errors:
                for msg in errors:
                    st.error(msg)
                return

            data = {
                "gender": gender,
                "age_group": age_group,
                "bmi_category": bmi_category,
                "fitness_goal": fitness_goal,
                "activity_level": activity_level,
                "dietary_preference": dietary_preference,
                "medical_conditions": medical_conditions.strip() or "None",
                "allergies_intolerances": allergies_intolerances.strip() or "None",
            }

            if is_edit:
                with st.spinner("Saving changes…"):
                    result = update_profile(st.session_state["user_id"], data)
                if result.get("error"):
                    st.error(f"Update failed: {result.get('message')}")
                else:
                    st.session_state["profile_edit_mode"] = False
                    st.info("Profile saved. Your plan will refresh on the next visit to Dashboard.")
                    st.rerun()
            else:
                with st.spinner("Creating your profile…"):
                    result = create_profile(data)
                if result.get("error"):
                    st.error(f"Could not create profile: {result.get('message')}")
                else:
                    st.session_state["user_id"] = result["user_id"]
                    st.session_state["profile_complete"] = True
                    st.rerun()


def _render_profile_card(profile: dict) -> None:
    """Render a read-only two-column profile card."""
    st.subheader("Your Profile")

    fields = list(_FIELD_LABELS.items())
    mid = len(fields) // 2
    left_fields, right_fields = fields[:mid], fields[mid:]

    col_l, col_r = st.columns(2)

    with col_l:
        for key, label in left_fields:
            value = profile.get(key, "—") or "—"
            st.markdown(f"**{label}**")
            st.write(value)
            st.write("")

    with col_r:
        for key, label in right_fields:
            value = profile.get(key, "—") or "—"
            st.markdown(f"**{label}**")
            st.write(value)
            st.write("")

    st.markdown("---")
    if st.button("Edit profile", icon="✏️"):
        st.session_state["profile_edit_mode"] = True
        st.rerun()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render() -> None:
    if "profile_edit_mode" not in st.session_state:
        st.session_state["profile_edit_mode"] = False

    user_id = st.session_state.get("user_id")

    if user_id is None:
        _render_form(prefill=None)
        return

    if st.session_state["profile_edit_mode"]:
        profile = get_profile(user_id)
        if profile.get("error"):
            st.error(f"Could not load profile: {profile.get('message')}")
            return
        _render_form(prefill=profile)
        st.markdown("")
        if st.button("Cancel", use_container_width=False):
            st.session_state["profile_edit_mode"] = False
            st.rerun()
        return

    profile = get_profile(user_id)
    if profile.get("error"):
        st.error(f"Could not load profile: {profile.get('message')}")
        return

    _render_profile_card(profile)
