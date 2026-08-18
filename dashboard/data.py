"""Cached, read-only access to precomputed pipeline outputs (design doc §8.2).

The dashboard never imports model/train.py, never loads a model artifact, and
never calls .predict() — every number it shows was already computed and
persisted by `pipeline.py`. If these files are missing, run the pipeline
first: `python pipeline.py`.
"""

import numpy as np
import pandas as pd
import streamlit as st

from grading.grade import letter_grade_from_score
from storage.io import read_parquet


@st.cache_data
def load_final_report():
    """One row per real pick, 2019-2022 — features, real vs. predicted PPS,
    and BPA/grading columns (see pipeline.py's `assemble_final_report`)."""
    return read_parquet("pipeline/final_report.parquet")


@st.cache_data
def load_team_rollup():
    """One row per (team, draft_year) — headline_score/grade_letter."""
    return read_parquet("grading/team_rollup.parquet")


@st.cache_data
def load_available_pool():
    """Full BPA-ranked available pool at every real pick (Phase 5)."""
    return read_parquet("simulation/available_pool.parquet")


def compute_multiyear_grades(team_rollup: pd.DataFrame) -> pd.DataFrame:
    """Picks-weighted headline score/grade per team, aggregated across
    whatever draft years are present in `team_rollup` — filter by year
    before calling to scope the aggregate (e.g. to the dashboard's current
    year filter, or to a single team's full history for a report export).

    Factored out here — not st.cache_data'd, since it's a cheap pure-pandas
    transform of an already-cached load — so the dashboard's league
    leaderboard and Phase 10's report export share one implementation of the
    weighting formula and grade thresholds instead of each recomputing it.
    """
    if team_rollup.empty:
        return team_rollup.assign(n_picks=pd.Series(dtype=int), headline_score=pd.Series(dtype=float), grade_letter=pd.Series(dtype=str))

    agg = (
        team_rollup.groupby("team_abbreviation_espn")
        .apply(
            lambda g: pd.Series(
                {
                    "n_picks": g["n_picks"].sum(),
                    "headline_score": np.average(g["headline_score"], weights=g["n_picks"]),
                }
            )
        )
        .reset_index()
    )
    agg["grade_letter"] = agg["headline_score"].map(letter_grade_from_score)
    return agg
