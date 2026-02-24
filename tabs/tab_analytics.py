"""Tab 3 — Analytics."""
from datetime import date

import streamlit as st

from database.db import (
    get_newsletters, upsert_analytics_snapshot, get_analytics_snapshots,
    upsert_post_analytics, get_post_analytics,
)
from substack.analytics import (
    fetch_summary, fetch_post_stats,
    parse_summary_to_db_format, parse_post_stats_to_db,
)
from substack.auth import build_session, SubstackAuthError
from utils.logger import get_logger

log = get_logger(__name__)

DATE_RANGE_OPTIONS = {"7 days": 7, "30 days": 30, "90 days": 90}


def render():
    st.header("Analytics")

    newsletters = get_newsletters()
    if not newsletters:
        st.warning("No newsletters found. Create one in Tab 1 first.")
        return

    nl_map = {f"{n['name']} ({n['language']})": n for n in newsletters}
    selected_label = st.selectbox("Select Newsletter", list(nl_map.keys()), key="analytics_nl_select")
    nl = nl_map[selected_label]

    col1, col2 = st.columns([2, 1])
    with col1:
        range_label = st.selectbox("Date Range", list(DATE_RANGE_OPTIONS.keys()), index=1, key="analytics_date_range")
    with col2:
        st.write("")
        st.write("")
        refresh_btn = st.button("Refresh Stats", type="primary", key="analytics_refresh_btn")

    days = DATE_RANGE_OPTIONS[range_label]

    if refresh_btn:
        cookie = st.session_state.get("substack_cookie", "")
        if not cookie:
            st.error("No Substack cookie. Paste it in the sidebar.")
        elif not nl.get("substack_url"):
            st.error("No Substack URL linked to this newsletter.")
        else:
            subdomain = (
                nl["substack_url"]
                .replace("https://", "")
                .replace("http://", "")
                .split(".substack.com")[0]
            )
            with st.spinner("Fetching analytics from Substack..."):
                try:
                    session = build_session(cookie)

                    # Fetch summary
                    summary_raw = fetch_summary(session, subdomain, days)
                    if summary_raw:
                        summary_data = parse_summary_to_db_format(summary_raw, days)
                        upsert_analytics_snapshot(
                            nl["id"], str(date.today()), summary_data
                        )
                        st.success("Summary stats updated.")
                    else:
                        st.warning(
                            "Could not fetch summary. Endpoint may be unavailable. "
                            "Showing cached data."
                        )

                    # Fetch post stats
                    posts_raw = fetch_post_stats(session, subdomain, days)
                    if posts_raw:
                        for post in posts_raw:
                            post_data = parse_post_stats_to_db(post)
                            if post_data.get("post_id"):
                                upsert_post_analytics(nl["id"], post_data["post_id"], post_data)
                        st.success(f"Updated stats for {len(posts_raw)} posts.")
                    else:
                        st.warning("No post stats available.")

                except SubstackAuthError as exc:
                    st.error(f"Auth error: {exc}")
                except Exception as exc:
                    st.error(f"Error fetching analytics: {exc}")

    # ===========================================================
    # Display Charts
    # ===========================================================
    snapshots = get_analytics_snapshots(nl["id"], days)
    post_stats = get_post_analytics(nl["id"])

    if not snapshots and not post_stats:
        st.info("No analytics data yet. Click 'Refresh Stats' to fetch from Substack.")
        return

    # KPI Cards (latest snapshot)
    if snapshots:
        latest = snapshots[-1]
        st.subheader("Current Metrics")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Subscribers", latest.get("total_subscribers") or "—")
        k2.metric("Paid Subscribers", latest.get("paid_subscribers") or "—")
        k3.metric("Free Subscribers", latest.get("free_subscribers") or "—")
        open_rate = latest.get("open_rate_30d")
        k4.metric("30-day Open Rate", f"{open_rate:.1%}" if open_rate else "—")

    # Subscriber growth chart
    if len(snapshots) > 1:
        import plotly.graph_objects as go
        import pandas as pd

        st.subheader("Subscriber Growth")
        df_snap = pd.DataFrame(snapshots)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_snap["snapshot_date"],
            y=df_snap["total_subscribers"],
            mode="lines+markers",
            name="Total Subscribers",
            line=dict(color="#7C3AED", width=2),
        ))
        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Subscribers",
            hovermode="x unified",
            height=350,
        )
        st.plotly_chart(fig, use_container_width=True)

    # Per-post open rate chart
    if post_stats:
        import plotly.graph_objects as go
        import pandas as pd

        st.subheader("Open Rate by Post")
        df_posts = pd.DataFrame(post_stats)
        df_posts = df_posts[df_posts["open_rate"].notna()].tail(15)

        if not df_posts.empty:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=df_posts["post_title"].fillna(df_posts["post_id"]),
                y=df_posts["open_rate"],
                marker_color="#7C3AED",
            ))
            fig2.update_layout(
                xaxis_title="Post",
                yaxis_title="Open Rate",
                yaxis_tickformat=".0%",
                height=400,
                xaxis_tickangle=-30,
            )
            st.plotly_chart(fig2, use_container_width=True)

        # Post stats table
        st.subheader("Post Details")
        cols = [c for c in ["post_title", "published_at", "emails_sent",
                             "emails_opened", "open_rate", "total_views"] if c in df_posts.columns]
        st.dataframe(
            df_posts[cols].rename(columns={
                "post_title": "Title", "published_at": "Published",
                "emails_sent": "Sent", "emails_opened": "Opened",
                "open_rate": "Open Rate", "total_views": "Views",
            }),
            use_container_width=True,
            hide_index=True,
        )
