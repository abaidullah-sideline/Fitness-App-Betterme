from __future__ import annotations

import sys
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

# ---------------------------------------------------------------------------
# Session state constants
# ---------------------------------------------------------------------------

USER_ID_KEY = "user_id"
PROFILE_COMPLETE_KEY = "profile_complete"
ACTIVE_THREAD_KEY = "active_thread_id"
ACTIVE_PAGE_KEY = "active_page"

PAGES = ["Profile", "Dashboard", "Chatbot"]


def _init_session() -> None:
    defaults = {
        USER_ID_KEY: None,
        PROFILE_COMPLETE_KEY: False,
        ACTIVE_THREAD_KEY: None,
        ACTIVE_PAGE_KEY: "Profile",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ---------------------------------------------------------------------------
# Navigation bar
# ---------------------------------------------------------------------------

def _render_nav() -> None:
    profile_complete = st.session_state[PROFILE_COMPLETE_KEY]

    st.markdown("## FitAI")
    cols = st.columns(len(PAGES))

    for col, page in zip(cols, PAGES):
        with col:
            is_active = st.session_state[ACTIVE_PAGE_KEY] == page
            disabled = page == "Dashboard" and not profile_complete

            label = f"**{page}**" if is_active else page
            if st.button(label, key=f"nav_{page}", disabled=disabled, use_container_width=True):
                st.session_state[ACTIVE_PAGE_KEY] = page
                st.rerun()

    st.divider()


# ---------------------------------------------------------------------------
# Page routing
# ---------------------------------------------------------------------------

def _route() -> None:
    page = st.session_state[ACTIVE_PAGE_KEY]

    if page == "Dashboard" and not st.session_state[PROFILE_COMPLETE_KEY]:
        st.session_state[ACTIVE_PAGE_KEY] = "Profile"
        st.warning("Please complete your profile first.")
        page = "Profile"

    if page == "Profile":
        from frontend.pages.profile import render
        render()
    elif page == "Dashboard":
        from frontend.pages.dashboard import render
        render()
    elif page == "Chatbot":
        from frontend.pages.chat import render
        render()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

st.set_page_config(page_title="FitAI", page_icon="💪", layout="wide")

_init_session()
_render_nav()
_route()
