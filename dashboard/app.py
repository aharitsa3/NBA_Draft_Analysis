"""NBA Draft Analysis dashboard (design doc §8.2) — Streamlit skeleton reading
only precomputed pipeline outputs (`processed_data/`), no live model
inference. Every projection metric is labeled "Projected Production Score" /
"PPS" — never VORP (§2's naming rule).

Phase 5.1 (positional-fit-adjusted ranking) was not built for this POC, so
every ranking shown here is Pure BPA only — that's called out explicitly
rather than silently presenting BPA as if it were the only possible view.

Run with: streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# `streamlit run` puts this script's own directory (dashboard/) at the front of
# sys.path instead of the project root, so the absolute `dashboard.*` /
# `grading.*` / `reports.*` / `storage.*` imports below can't resolve as
# packages unless we add the project root ourselves first.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.graph_objects as go
import streamlit as st

from dashboard.data import compute_multiyear_grades, load_available_pool, load_final_report, load_team_rollup
from dashboard.palette import (
    BASELINE,
    GRIDLINE,
    MUTED_INK,
    PRIMARY_INK,
    SEQUENTIAL_BLUE,
    SERIES_BLUE,
    SURFACE,
)
from reports.export import generate_report_html, generate_report_pdf
from reports.narrative import build_prompt_text, generate_narrative, ingest_manual_narrative, load_cached_narrative

st.set_page_config(page_title="NBA Draft Analysis", layout="wide")

st.title("NBA Draft Analysis")
st.caption(
    "Reads only precomputed pipeline outputs (`python pipeline.py`) — no live model inference. "
    "Rankings shown are **Pure Best-Player-Available (BPA)** only; the optional positional-fit-adjusted "
    "ranking (design doc §6.2.2) was not built for this POC."
)
st.caption(
    "**PPS = Projected Production Score** — mean Game Score across a player's real year-2 and "
    "year-3 NBA seasons, predicted from pre-draft NCAA stats. A proxy metric, not real VORP."
)

report = load_final_report()
team_rollup = load_team_rollup()
pool = load_available_pool()

all_teams = sorted(report["team_abbreviation_espn"].unique())
all_years = sorted(int(y) for y in report["draft_year"].unique())

with st.sidebar:
    st.header("Filters")
    selected_years = st.multiselect("Draft year", all_years, default=all_years)
    selected_team = st.selectbox("Team (for trend + drill-down)", all_teams)

    st.header("Export")
    st.caption(f"{selected_team}'s report, scoped to the draft year(s) selected above.")
    export_html_str = generate_report_html(selected_team, selected_years)
    st.download_button(
        "Download HTML report",
        data=export_html_str,
        file_name=f"{selected_team}_report.html",
        mime="text/html",
    )
    if st.button("Prepare PDF report"):
        with st.spinner("Rendering PDF..."):
            pdf_bytes = generate_report_pdf(selected_team, selected_years)
        st.download_button(
            "Download PDF report",
            data=pdf_bytes,
            file_name=f"{selected_team}_report.pdf",
            mime="application/pdf",
        )

if not selected_years:
    st.warning("Select at least one draft year.")
    st.stop()

# ---------------------------------------------------------------------------
# Section A — League aggregate grade view (headline score / letter grade per team)
# ---------------------------------------------------------------------------
st.header("League Aggregate Grades")
st.caption(f"Draft year(s): {', '.join(str(y) for y in selected_years)}")

league = team_rollup[team_rollup["draft_year"].isin(selected_years)]
league_agg = compute_multiyear_grades(league)

if league_agg.empty:
    st.info("No picks in the selected draft year(s).")
else:
    league_agg = league_agg.sort_values("headline_score", ascending=True)  # ascending for a top-to-bottom horizontal bar

    bar_colors = [SEQUENTIAL_BLUE[3]] * len(league_agg)
    fig = go.Figure(
        go.Bar(
            x=league_agg["headline_score"],
            y=league_agg["team_abbreviation_espn"],
            orientation="h",
            marker_color=bar_colors,
            text=league_agg["grade_letter"],
            textposition="outside",
            textfont=dict(color=PRIMARY_INK),
            customdata=league_agg[["n_picks"]].values,
            hovertemplate="%{y}: headline score %{x:.2f}<br>Grade %{text} · %{customdata[0]} pick(s)<extra></extra>",
        )
    )
    fig.update_layout(
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        xaxis=dict(title="Headline score (higher = closer to the model's own BPA-optimal picks)", gridcolor=GRIDLINE, color=MUTED_INK, zeroline=True, zerolinecolor=BASELINE),
        yaxis=dict(title=None, color=MUTED_INK),
        height=max(400, 24 * len(league_agg)),
        margin=dict(t=10, b=40, l=10, r=40),
    )
    st.plotly_chart(fig, width="stretch")

    with st.expander("View as table"):
        table = league_agg.sort_values("headline_score", ascending=False).rename(
            columns={
                "team_abbreviation_espn": "Team",
                "n_picks": "Picks",
                "headline_score": "Headline Score",
                "grade_letter": "Grade",
            }
        )[["Team", "Picks", "Headline Score", "Grade"]]
        st.dataframe(table.style.format({"Headline Score": "{:.2f}"}), width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Section B — Trend view (selected team's grade across 2019-2022)
# ---------------------------------------------------------------------------
st.header(f"{selected_team} — Grade Trend, 2019–2022")
st.caption("Always shows the full 2019–2022 range regardless of the draft-year filter above — that's what a trend is.")

team_trend = team_rollup[team_rollup["team_abbreviation_espn"] == selected_team].sort_values("draft_year")

if team_trend.empty:
    st.info(f"{selected_team} made no picks in this dataset (2019-2022).")
else:
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color=BASELINE, width=1, dash="dash"))
    fig.add_trace(
        go.Scatter(
            x=team_trend["draft_year"],
            y=team_trend["headline_score"],
            mode="lines+markers+text",
            line=dict(color=SERIES_BLUE, width=2),
            marker=dict(size=10, color=SERIES_BLUE),
            text=team_trend["grade_letter"],
            textposition="top center",
            textfont=dict(color=PRIMARY_INK),
            hovertemplate="Draft %{x}<br>Headline score %{y:.2f}<br>Grade %{text}<extra></extra>",
        )
    )
    fig.update_layout(
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        xaxis=dict(title="Draft year", tickmode="array", tickvals=all_years, gridcolor=GRIDLINE, color=MUTED_INK),
        yaxis=dict(title="Headline score", gridcolor=GRIDLINE, color=MUTED_INK, zeroline=False),
        showlegend=False,
        margin=dict(t=20, b=20, l=10, r=10),
        height=340,
    )
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# Section B.5 — Narrative report (design doc §7.4)
# ---------------------------------------------------------------------------
st.header(f"{selected_team} — Team Report")

cached_narrative = load_cached_narrative(selected_team)
if cached_narrative is not None:
    st.write(cached_narrative["narrative"])
    if cached_narrative["grounding_warnings"]:
        st.warning(
            "Grounding check flagged number(s) in this narrative that don't trace back "
            f"to the input data: {', '.join(cached_narrative['grounding_warnings'])}"
        )
    source_label = "pasted from claude.ai" if cached_narrative.get("source") == "manual" else "Anthropic API"
    st.caption(
        f"Generated {cached_narrative['generated_at']} ({source_label}) — cached; "
        "not re-sent to the API on this page load."
    )
else:
    st.caption("No cached report yet for this team's current data.")

with st.expander("Generate via Anthropic API (uses usage credits)"):
    if st.button("Generate / regenerate report", key="gen_narrative_api"):
        try:
            with st.spinner("Calling Claude..."):
                generate_narrative(selected_team, force=True)
            st.rerun()
        except Exception as e:
            st.error(f"Narrative generation failed: {e}")

with st.expander("Generate for free via claude.ai (copy/paste, no API key)"):
    st.caption(
        "1. Copy the prompt below into claude.ai (or any Claude chat). "
        "2. Paste Claude's reply into the box underneath. 3. Save it — it's cached exactly "
        "like an API-generated report."
    )
    st.text_area("Prompt to paste into claude.ai", value=build_prompt_text(selected_team), height=200, key="manual_prompt")
    pasted_reply = st.text_area("Paste Claude's reply here", height=150, key="manual_reply")
    if st.button("Save pasted narrative", key="save_manual_narrative"):
        try:
            ingest_manual_narrative(selected_team, pasted_reply)
            st.rerun()
        except Exception as e:
            st.error(f"Couldn't save that narrative: {e}")

# ---------------------------------------------------------------------------
# Section C — Pick-by-pick drill-down
# ---------------------------------------------------------------------------
st.header(f"{selected_team} — Pick-by-Pick Drill-Down")

team_picks = report[
    (report["team_abbreviation_espn"] == selected_team) & (report["draft_year"].isin(selected_years))
].sort_values(["draft_year", "pick"])

if team_picks.empty:
    st.info("No picks for this team in the selected draft year(s).")
else:
    display = team_picks.rename(
        columns={
            "draft_year": "Draft Year",
            "pick": "Pick",
            "player_name": "Player Selected",
            "predicted_pps_selected": "Predicted PPS",
            "actual_pps": "Actual PPS (yr2-3 avg)",
            "bpa_top_player": "#1 BPA Alternative",
            "bpa_top_predicted_pps": "#1 Alternative Predicted PPS",
            "rank_differential": "Rank Differential",
            "value_gap": "Value Gap (PPS pts)",
        }
    )[
        [
            "Draft Year",
            "Pick",
            "Player Selected",
            "Predicted PPS",
            "Actual PPS (yr2-3 avg)",
            "#1 BPA Alternative",
            "#1 Alternative Predicted PPS",
            "Rank Differential",
            "Value Gap (PPS pts)",
        ]
    ]
    st.dataframe(
        display.style.format(
            {
                "Predicted PPS": "{:.2f}",
                "Actual PPS (yr2-3 avg)": "{:.2f}",
                "#1 Alternative Predicted PPS": "{:.2f}",
                "Value Gap (PPS pts)": "{:.2f}",
            },
            na_rep="N/A",
        ),
        width="stretch",
        hide_index=True,
    )

    fig = go.Figure(
        go.Bar(
            x=[f"{int(y)} · Pk {int(p)}" for y, p in zip(team_picks["draft_year"], team_picks["pick"])],
            y=team_picks["value_gap"],
            marker_color=SEQUENTIAL_BLUE[3],
            customdata=team_picks[["player_name", "bpa_top_player"]].values,
            hovertemplate="%{x}<br>%{customdata[0]} (selected)<br>Value gap vs. %{customdata[1]}: %{y:.2f} PPS pts<extra></extra>",
        )
    )
    fig.update_layout(
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        yaxis=dict(title="Value gap (PPS points)", gridcolor=GRIDLINE, color=MUTED_INK),
        xaxis=dict(color=MUTED_INK),
        margin=dict(t=20, b=20, l=10, r=10),
        height=320,
    )
    st.plotly_chart(fig, width="stretch")

    st.subheader("Full BPA-ranked pool at time of pick")
    for _, row in team_picks.iterrows():
        with st.expander(f"{int(row['draft_year'])} · Pick {int(row['pick'])} — {row['player_name']}"):
            pool_at_pick = pool[
                (pool["draft_year"] == row["draft_year"]) & (pool["pick"] == row["pick"])
            ].sort_values("rank_in_pool")
            pool_display = pool_at_pick.rename(
                columns={"rank_in_pool": "BPA Rank", "player_name": "Player", "predicted_pps": "Predicted PPS"}
            )[["BPA Rank", "Player", "Predicted PPS"]]

            def _highlight(col, selected_name=row["player_name"]):
                return ["background-color: #cde2fb" if v == selected_name else "" for v in col]

            st.dataframe(
                pool_display.style.apply(_highlight, subset=["Player"]).format({"Predicted PPS": "{:.2f}"}),
                width="stretch",
                hide_index=True,
            )
