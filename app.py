"""Streamlit entry point — Language Learning Newsletter Dashboard."""
import sys
from pathlib import Path

# Ensure project root is on sys.path so all imports work
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from config.settings import ANTHROPIC_API_KEY, OPENAI_API_KEY, SUBSTACK_COOKIE  # noqa: F401
from database.db import init_db
from utils.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Language Learning Newsletter Dashboard",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# DB initialisation (idempotent)
# ---------------------------------------------------------------------------
@st.cache_resource
def _init():
    init_db()
    log.info("Database initialised")

_init()

# ---------------------------------------------------------------------------
# Sidebar — API key status + cookie input
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📚 Newsletter Dashboard")
    st.divider()

    # API key status
    st.subheader("API Keys")
    col_a, col_b = st.columns(2)
    col_a.metric("Anthropic", "✅" if ANTHROPIC_API_KEY else "❌")
    col_b.metric("OpenAI", "✅" if OPENAI_API_KEY else "❌")

    if not ANTHROPIC_API_KEY or not OPENAI_API_KEY:
        st.warning(
            "Add your API keys to the `.env` file and restart Streamlit.\n\n"
            "See `.env.example` for the required variables."
        )

    st.divider()

    # Substack cookie input — persists in session state across tabs
    st.subheader("Substack Auth")
    if "substack_cookie" not in st.session_state:
        st.session_state["substack_cookie"] = SUBSTACK_COOKIE or ""

    cookie_input = st.text_area(
        "Session Cookie",
        value=st.session_state["substack_cookie"],
        height=80,
        placeholder="Paste Substack cookie here",
        help=(
            "Log in to Substack → open DevTools (F12) → Network tab → "
            "click any request → find the 'Cookie' request header → copy its value."
        ),
        key="sidebar_cookie_input",
    )
    if cookie_input != st.session_state["substack_cookie"]:
        st.session_state["substack_cookie"] = cookie_input

    if st.session_state["substack_cookie"]:
        st.success("Cookie set")
    else:
        st.info("No cookie — Substack features disabled")

    st.divider()
    st.caption("v1.0.0 · Claude Sonnet 4.6 · DALL-E 3")

# ---------------------------------------------------------------------------
# Tab routing
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "⚙️ Newsletter Setup",
    "✍️ Content Generation",
    "📊 Analytics",
    "📱 Social Media",
    "🤖 Automation",
])

with tab1:
    from tabs.tab_create import render as render_create
    render_create()

with tab2:
    from tabs.tab_content import render as render_content
    render_content()

with tab3:
    from tabs.tab_analytics import render as render_analytics
    render_analytics()

with tab4:
    from tabs.tab_social import render as render_social
    render_social()

with tab5:
    from tabs.tab_automation import render as render_automation
    render_automation()
