"""Tab 1 — Newsletter Setup."""
import streamlit as st

from config.languages import LANGUAGE_OPTIONS, EXAM_CONFIGS
from database.db import insert_newsletter, get_newsletters
from utils.logger import get_logger

log = get_logger(__name__)


def render():
    st.header("Newsletter Setup")
    st.markdown(
        "Configure a new language learning newsletter. "
        "The Substack URL is optional and used only for analytics."
    )

    with st.form("create_newsletter_form"):
        col1, col2 = st.columns(2)

        with col1:
            newsletter_name = st.text_input(
                "Newsletter Name",
                placeholder="e.g. Japanese Journey",
            )
            language_choice = st.selectbox(
                "Language",
                list(LANGUAGE_OPTIONS.keys()),
            )
            custom_language = ""
            if language_choice == "Custom Language":
                custom_language = st.text_input("Enter Language Name")

        with col2:
            exam_key = LANGUAGE_OPTIONS.get(language_choice, "custom")
            if exam_key != "custom" and exam_key in EXAM_CONFIGS:
                exam_label = EXAM_CONFIGS[exam_key].exam
                st.text_input("Exam / Framework", value=exam_label, disabled=True)
            else:
                exam_label = st.text_input(
                    "Exam / Framework",
                    placeholder="e.g. Goethe-Zertifikat",
                )

            substack_url = st.text_input(
                "Substack URL (for analytics only)",
                placeholder="https://yournewsletter.substack.com",
                help="Optional. Used by the Analytics tab to fetch post stats.",
            )

        submitted = st.form_submit_button("Save Newsletter", type="primary")

    if submitted:
        errors = []
        if not newsletter_name.strip():
            errors.append("Newsletter name is required.")
        language = (
            custom_language.strip()
            if language_choice == "Custom Language"
            else language_choice.split(" (")[0]
        )
        if not language:
            errors.append("Language is required.")

        if errors:
            for err in errors:
                st.error(err)
            return

        # Resolve exam label
        if exam_key in EXAM_CONFIGS:
            exam = EXAM_CONFIGS[exam_key].exam
        elif isinstance(exam_label, str) and exam_label.strip():
            exam = exam_label.strip()
        else:
            exam = "Custom"

        try:
            nl_id = insert_newsletter(
                name=newsletter_name.strip(),
                language=language,
                exam=exam,
                substack_url=substack_url.strip() or None,
                substack_pub_id=None,
            )
            st.success(f"Newsletter **{newsletter_name.strip()}** saved! (ID: {nl_id})")
        except Exception as exc:
            log.error("Newsletter save error: %s", exc)
            st.error(f"Database error: {exc}")
            return

    # --- Existing newsletters table ---
    st.divider()
    st.subheader("Existing Newsletters")
    newsletters = get_newsletters()
    if not newsletters:
        st.info("No newsletters yet. Create one above.")
    else:
        import pandas as pd
        df = pd.DataFrame(newsletters)[
            ["id", "name", "language", "exam", "substack_url", "created_at"]
        ]
        df.columns = ["ID", "Name", "Language", "Exam", "Substack URL", "Created"]
        st.dataframe(df, use_container_width=True, hide_index=True)
