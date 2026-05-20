from __future__ import annotations

import pathlib
import re
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from frontend.api_client import delete_thread, get_chats, get_thread, send_message

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://[^\s\)\]\"']+")
_GIF_RE = re.compile(r"[\w./\\-]+\.gif", re.IGNORECASE)


def _extract_urls(text: str) -> list[str]:
    return _URL_RE.findall(text)


def _extract_gif_paths(text: str) -> list[str]:
    return _GIF_RE.findall(text)


def _resolve_gif(raw_path: str) -> pathlib.Path | None:
    """Return an absolute path to the GIF if it exists on disk."""
    candidate = pathlib.Path(raw_path)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    absolute = PROJECT_ROOT / raw_path
    if absolute.exists():
        return absolute
    return None


# ---------------------------------------------------------------------------
# Source parsing — retrieved_sources from the chat API
# ---------------------------------------------------------------------------

def _parse_sources(sources: list[str]) -> tuple[list[str], list[str]]:
    """Return (gif_absolute_paths, youtube_urls) extracted from raw source strings."""
    gifs: list[str] = []
    yt_urls: list[str] = []
    for src in sources:
        if src.startswith("[GIF]"):
            # Format: "[GIF] name — muscle, diff | file_path"
            parts = src.split("|")
            if len(parts) >= 2:
                raw = parts[-1].strip()
                resolved = _resolve_gif(raw)
                if resolved:
                    gifs.append(str(resolved))
        elif src.startswith("[YouTube]"):
            # Format: "[YouTube] title | url | tags: ..."
            parts = src.split("|")
            if len(parts) >= 2:
                url = parts[1].strip()
                if url.startswith("http"):
                    yt_urls.append(url)
    return gifs, yt_urls


# ---------------------------------------------------------------------------
# Message rendering
# ---------------------------------------------------------------------------

def _render_message_content(role: str, content: str, sources: list[str] | None = None) -> None:
    if role == "user":
        st.write(content)
        return

    # Assistant — render text, then surface media from both message body and sources
    st.markdown(content)

    # Collect GIFs and URLs from the message body itself
    body_gifs = [p for raw in _extract_gif_paths(content) if (p := _resolve_gif(raw))]
    body_urls = _extract_urls(content)

    # Collect from retrieved_sources attached to this message
    src_gifs: list[str] = []
    src_urls: list[str] = []
    if sources:
        src_gifs, src_urls = _parse_sources(sources)

    all_gifs = list({str(g) for g in body_gifs} | set(src_gifs))
    all_urls = list(dict.fromkeys(body_urls + src_urls))  # deduplicate, preserve order

    # Render GIFs
    for gif_path in all_gifs:
        try:
            st.image(gif_path, width=300)
        except Exception:
            pass

    # Render YouTube links that aren't already in the markdown text
    yt_links = [u for u in all_urls if "youtube" in u or "youtu.be" in u]
    if yt_links:
        st.markdown("**📺 Related videos:**")
        for url in yt_links:
            st.markdown(f"- [{url}]({url})")


# ---------------------------------------------------------------------------
# CSS injection
# ---------------------------------------------------------------------------

def _inject_css() -> None:
    st.markdown(
        """
        <style>
        /* Tighten sidebar thread list */
        .thread-label {
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 100%;
            display: block;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _get_or_create_guest_id() -> str:
    """Return a stable guest UUID for anonymous chat sessions."""
    import uuid

    if "guest_chat_id" not in st.session_state:
        st.session_state["guest_chat_id"] = f"guest_{uuid.uuid4()}"
    return st.session_state["guest_chat_id"]


def _clear_thread() -> None:
    st.session_state["active_thread_id"] = None
    st.session_state["chat_messages"] = []


def _load_thread(thread_id: str) -> None:
    history = get_thread(thread_id)
    if history.get("error"):
        st.toast(f"Could not load thread: {history.get('message')}", icon="⚠️")
        return
    st.session_state["active_thread_id"] = thread_id
    st.session_state["chat_messages"] = history.get("messages", [])


# ---------------------------------------------------------------------------
# Left sidebar column
# ---------------------------------------------------------------------------

def _render_sidebar(user_id: str) -> None:
    # New chat
    if st.button("➕  New chat", use_container_width=True, type="primary"):
        _clear_thread()
        st.rerun()

    st.markdown("---")
    st.caption("Recent conversations")

    threads = get_chats(user_id)

    if not threads:
        st.caption("No conversations yet.")
        return

    active_id = st.session_state.get("active_thread_id")

    for thread in threads:
        tid = thread.get("thread_id", "")
        title = thread.get("title", "Untitled")[:40]
        is_active = tid == active_id

        col_btn, col_del = st.columns([5, 1])

        with col_btn:
            btn_type = "primary" if is_active else "secondary"
            if st.button(title, key=f"thread_{tid}", use_container_width=True, type=btn_type):
                _load_thread(tid)
                st.rerun()

        with col_del:
            if st.button("✕", key=f"del_{tid}", help="Delete thread"):
                delete_thread(tid)
                if active_id == tid:
                    _clear_thread()
                st.rerun()


# ---------------------------------------------------------------------------
# Right chat panel
# ---------------------------------------------------------------------------

def _render_chat_panel(user_id: str) -> None:
    messages: list[dict] = st.session_state.get("chat_messages", [])

    # Message history
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        sources = msg.get("sources")
        with st.chat_message(role):
            _render_message_content(role, content, sources)

    # Chat input — Streamlit renders this at the bottom of the app
    if prompt := st.chat_input("Ask about workouts, meals, or nutrition..."):
        # Optimistic UI: append user message before the API call
        if "chat_messages" not in st.session_state:
            st.session_state["chat_messages"] = []
        st.session_state["chat_messages"].append({"role": "user", "content": prompt})

        thread_id = st.session_state.get("active_thread_id")

        with st.spinner("Thinking..."):
            result = send_message(user_id, thread_id, prompt)

        if result.get("error"):
            st.error(f"Chat error: {result.get('message')}")
        else:
            # If a new thread was created, store its ID
            new_tid = result.get("thread_id")
            if new_tid:
                st.session_state["active_thread_id"] = new_tid

            ai_msg: dict = {
                "role": "assistant",
                "content": result.get("response", ""),
            }
            sources = result.get("retrieved_sources") or []
            if sources:
                ai_msg["sources"] = sources

            st.session_state["chat_messages"].append(ai_msg)

        st.rerun()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render() -> None:
    _inject_css()

    user_id: str | None = st.session_state.get("user_id")

    if not user_id:
        st.info("Complete your profile to get personalised responses.")
        user_id = _get_or_create_guest_id()

    # Ensure chat state keys exist
    st.session_state.setdefault("chat_messages", [])
    st.session_state.setdefault("active_thread_id", None)

    left_col, right_col = st.columns([1, 3])

    with left_col:
        _render_sidebar(user_id)

    with right_col:
        st.subheader("FitAI Chat")
        _render_chat_panel(user_id)
