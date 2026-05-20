from __future__ import annotations

import sys
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import math
import re
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import streamlit as st

from frontend.api_client import (
    edit_plan as api_edit_plan,
    get_plan,
    reset_plan as api_reset_plan,
    toggle_checkbox,
)

# Column width ratios: checkbox | sr | day | workout | breakfast | lunch | dinner
_COL_RATIOS = [0.45, 0.45, 1.4, 3.5, 2, 2, 2]
_DAYS_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_BURNED_COLOR = "#FF6B6B"
_INTAKE_COLOR = "#6BCB77"


# ---------------------------------------------------------------------------
# CSS injection
# ---------------------------------------------------------------------------

def _inject_css() -> None:
    st.markdown(
        """
        <style>
        .today-badge {
            display: inline-block;
            background: #3B82F6;
            color: white;
            font-size: 10px;
            font-weight: 700;
            border-radius: 4px;
            padding: 1px 5px;
            margin-left: 4px;
            vertical-align: middle;
        }
        .plan-header {
            font-weight: 700;
            font-size: 13px;
            color: #6B7280;
            padding: 6px 0;
            border-bottom: 2px solid #E5E7EB;
            margin-bottom: 4px;
        }
        .stat-section-title {
            font-size: 16px;
            font-weight: 600;
            margin-top: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today_name() -> str:
    return datetime.now().strftime("%A")


def _week_dates() -> dict[str, str]:
    """Return {day_name: 'May 20'} for the current Mon–Sun week."""
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    return {
        day: (monday + timedelta(days=i)).strftime("%b %d")
        for i, day in enumerate(_DAYS_ORDER)
    }


def _checkbox_callback(day_name: str, plan_id: str, user_id: str) -> None:
    """Called by st.checkbox on_change; persists toggle and stores DailyStats."""
    is_complete = st.session_state[f"check_{day_name}"]
    result = toggle_checkbox(user_id, plan_id, day_name, is_complete)
    logs: dict = st.session_state.setdefault("day_logs", {})
    if result.get("error"):
        st.toast(f"Could not save: {result.get('message')}", icon="⚠️")
        # Roll back the visual state
        st.session_state[f"check_{day_name}"] = not is_complete
    else:
        logs[day_name] = {"is_complete": is_complete, "stats": result}


def _init_checkbox_state(days: list[dict]) -> None:
    """Set checkbox session-state keys only on first render, not on reruns."""
    day_logs: dict = st.session_state.get("day_logs", {})
    for day in days:
        key = f"check_{day['day']}"
        if key not in st.session_state:
            st.session_state[key] = day_logs.get(day["day"], {}).get("is_complete", False)


_TEXT_COLOR = "#E5E7EB"      # light grey — readable on both dark and light themes
_SPINE_COLOR = "#4B5563"     # muted border


def _calories_timeline_chart(checked_days: list, week_dates: dict[str, str]):
    """Cumulative line chart: total workout calories burned vs food intake as days are completed."""
    labels, cum_burned, cum_food = [], [], []
    total_burned = total_food = 0

    for day_name, info in checked_days:
        stats = info["stats"]
        date_str = week_dates.get(day_name, "")
        labels.append(f"{day_name[:3]}\n{date_str}")

        total_burned += stats.get("est_calories_burned", 0)

        # Prefer the dataset's direct Calories field; fall back to macro computation
        food_kcal = stats.get("food_calories_kcal", 0)
        if not food_kcal:
            fat = stats.get("fat_g", 0)
            carbs = stats.get("carbs_g", 0)
            protein = stats.get("protein_g", 0)
            food_kcal = round(fat * 9 + carbs * 4 + protein * 4)

        total_food += food_kcal
        cum_burned.append(total_burned)
        cum_food.append(total_food)

    n = len(labels)
    x = list(range(n))

    fig, ax = plt.subplots(figsize=(max(5, n * 1.8), 4))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    ax.plot(x, cum_burned, marker="o", linewidth=2, markersize=6,
            label="Burned (workout)", color=_BURNED_COLOR)
    ax.plot(x, cum_food, marker="s", linewidth=2, markersize=6,
            label="Intake (food)", color=_INTAKE_COLOR)

    for xi, (yb, yf) in enumerate(zip(cum_burned, cum_food)):
        ax.text(xi, yb + max(cum_food[-1], cum_burned[-1]) * 0.02, str(int(yb)),
                ha="center", va="bottom", fontsize=7, color=_BURNED_COLOR)
        ax.text(xi, yf - max(cum_food[-1], cum_burned[-1]) * 0.04, str(int(yf)),
                ha="center", va="top", fontsize=7, color=_INTAKE_COLOR)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9, color=_TEXT_COLOR)
    ax.set_ylabel("Cumulative kcal", fontsize=9, color=_TEXT_COLOR)
    ax.set_title("Cumulative Calories — Burned vs Food Intake", fontsize=10,
                 pad=10, color=_TEXT_COLOR)

    legend = ax.legend(fontsize=8, frameon=False)
    for text in legend.get_texts():
        text.set_color(_TEXT_COLOR)

    for spine in ax.spines.values():
        spine.set_edgecolor(_SPINE_COLOR)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.tick_params(axis="both", labelsize=8, colors=_TEXT_COLOR)
    ax.yaxis.label.set_color(_TEXT_COLOR)

    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------

def _render_header() -> None:
    cols = st.columns(_COL_RATIOS)
    labels = ["☑", "Sr.", "Day", "Workout Plan", "Breakfast", "Lunch", "Dinner"]
    for col, label in zip(cols, labels):
        col.markdown(f'<div class="plan-header">{label}</div>', unsafe_allow_html=True)


def _render_row(day: dict, plan_id: str, user_id: str, today: str, week_dates: dict[str, str]) -> None:
    day_name: str = day["day"]
    is_today = day_name == today
    date_str = week_dates.get(day_name, "")

    cols = st.columns(_COL_RATIOS)

    # Checkbox
    with cols[0]:
        st.checkbox(
            "",
            key=f"check_{day_name}",
            on_change=_checkbox_callback,
            args=(day_name, plan_id, user_id),
            label_visibility="collapsed",
        )

    # Sr.
    cols[1].write(day["sr"])

    # Day + date (with TODAY badge when applicable)
    with cols[2]:
        if is_today:
            st.markdown(
                f"**{day_name}**<br>"
                f"<small style='color:#3B82F6'>{date_str}</small> "
                f"<span class='today-badge'>TODAY</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"**{day_name}**<br>"
                f"<small style='color:#9CA3AF'>{date_str}</small>",
                unsafe_allow_html=True,
            )

    # Workout
    workout = day.get("workout_plan", "")
    with cols[3]:
        if len(workout) > 80:
            st.write(workout[:80] + "…")
            with st.expander("See full workout"):
                st.write(workout)
        else:
            st.write(workout)

    # Meals
    cols[4].write(day.get("breakfast", ""))
    cols[5].write(day.get("lunch", ""))
    cols[6].write(day.get("dinner", ""))

    st.divider()


def _render_table(plan: dict, user_id: str) -> None:
    days: list[dict] = plan.get("days", [])
    plan_id: str = plan.get("plan_id", "")
    today = _today_name()
    dates = _week_dates()

    _render_header()
    for day in days:
        _render_row(day, plan_id, user_id, today, dates)


# ---------------------------------------------------------------------------
# Edit bar
# ---------------------------------------------------------------------------

def _render_edit_bar(plan: dict, user_id: str) -> None:
    st.markdown("### Modify your plan")
    col_input, col_apply, col_reset = st.columns([5, 1, 1.5])

    with col_input:
        command = st.text_input(
            "Modify your plan",
            placeholder="e.g. Replace Wednesday workout with yoga",
            label_visibility="collapsed",
            key="edit_command_input",
        )

    with col_apply:
        apply_clicked = st.button("Apply", type="primary", use_container_width=True)

    with col_reset:
        reset_clicked = st.button("Reset to original", use_container_width=True)

    if apply_clicked:
        if not command.strip():
            st.warning("Enter an edit command first.")
        else:
            current_days = plan.get("days", [])
            with st.spinner("Applying edit…"):
                result = api_edit_plan(user_id, command.strip(), current_days)
            if result.get("error"):
                st.error(f"Edit failed: {result.get('message')}")
            else:
                st.session_state["current_plan"] = result
                st.rerun()

    if reset_clicked:
        with st.spinner("Resetting plan…"):
            result = api_reset_plan(user_id, plan.get("plan_id", ""))
        if result.get("error"):
            st.error(f"Reset failed: {result.get('message')}")
        else:
            # Clear day_logs and checkbox states so the table re-initialises
            st.session_state["day_logs"] = {}
            st.session_state["current_plan"] = result
            for day in result.get("days", []):
                st.session_state[f"check_{day['day']}"] = False
            st.rerun()


# ---------------------------------------------------------------------------
# Stats section
# ---------------------------------------------------------------------------

def _render_stats(plan: dict) -> None:
    day_logs: dict = st.session_state.get("day_logs", {})
    checked_days = [
        (name, info)
        for name, info in day_logs.items()
        if info.get("is_complete") and info.get("stats")
    ]

    if not checked_days:
        return

    st.markdown("---")
    st.markdown("## Daily Stats")

    # Weekly completion progress
    total_complete = sum(1 for info in day_logs.values() if info.get("is_complete"))
    st.progress(total_complete / 7, text=f"Weekly completion: {total_complete} / 7 days")
    st.write("")

    # Sort by day order
    order = {d: i for i, d in enumerate(_DAYS_ORDER)}
    checked_days.sort(key=lambda x: order.get(x[0], 99))

    week_dates = _week_dates()

    # Timeline chart spanning all completed days
    fig = _calories_timeline_chart(checked_days, week_dates)
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)
    st.write("")

    # Per-day metric cards
    for day_name, info in checked_days:
        stats: dict = info["stats"]
        date_str = week_dates.get(day_name, "")
        st.markdown(
            f'<div class="stat-section-title">{day_name}'
            f' <small style="color:#9CA3AF;font-weight:400">{date_str}</small></div>',
            unsafe_allow_html=True,
        )
        fat = stats.get("fat_g", 0)
        show_fat = fat > 0
        cols = st.columns(4 if show_fat else 3)
        cols[0].metric("🔥 Calories Burned", f"{stats.get('est_calories_burned', 0)} kcal")
        cols[1].metric("🥩 Protein", f"{stats.get('protein_g', 0)} g")
        cols[2].metric("🍞 Carbohydrates", f"{stats.get('carbs_g', 0)} g")
        if show_fat:
            cols[3].metric("🫒 Fat", f"{fat} g")
        st.write("")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render() -> None:
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.error("Please complete your profile to view your plan.")
        return

    _inject_css()
    st.header("Your Weekly Plan")

    # Fetch plan (cache in session_state; re-fetch if not present)
    if not st.session_state.get("current_plan"):
        with st.spinner("Generating your personalised plan…"):
            plan = get_plan(user_id)
        if plan.get("error"):
            st.error(f"Could not load plan: {plan.get('message')}")
            return
        st.session_state["current_plan"] = plan
        st.session_state["day_logs"] = {}

    plan = st.session_state["current_plan"]

    if plan.get("error"):
        st.error(f"Plan error: {plan.get('message')}")
        return

    _init_checkbox_state(plan.get("days", []))
    _render_table(plan, user_id)
    _render_edit_bar(plan, user_id)
    _render_stats(plan)
