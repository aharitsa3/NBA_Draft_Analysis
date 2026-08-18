"""Grading (design doc §6.3) — per-pick grades + team-level rollup, from
Phase 5's Pure BPA simulation output.

Phase 5.1 (positional-fit-adjusted ranking) was skipped as an optional
stretch goal per tasks.md, so only the required BPA-based metrics are
computed here — no fit-adjusted variant, no 2019/2020 coverage-gap flag
needed.

Run with: python -m grading.grade
"""

import pandas as pd

from storage.io import read_parquet, write_parquet

# (min composite z-score inclusive, letter), checked in order — a standard
# curved-grading convention (like a z-scored exam curve); necessarily a
# judgment call on where to draw the bands, documented here for transparency.
GRADE_THRESHOLDS = [
    (1.0, "A"),
    (0.5, "B+"),
    (0.0, "B"),
    (-0.5, "B-"),
    (-1.0, "C+"),
    (-1.5, "C"),
    (float("-inf"), "F"),
]


def letter_grade_from_score(z: float) -> str:
    """Public so the dashboard (Phase 8) can grade its own multi-year-weighted
    aggregates with the exact same curve, instead of re-deriving thresholds."""
    for threshold, letter in GRADE_THRESHOLDS:
        if z >= threshold:
            return letter
    return "F"


def build_pick_grades() -> pd.DataFrame:
    """Rank differential + value gap per pick (both BPA-required metrics)."""
    picks = read_parquet("simulation/picks.parquet")
    grades = picks.copy()
    grades["rank_differential"] = grades["bpa_rank_of_selected"] - 1
    grades["value_gap"] = grades["bpa_top_predicted_pps"] - grades["predicted_pps_selected"]
    return grades


def build_team_rollup(pick_grades: pd.DataFrame) -> pd.DataFrame:
    """One row per (team, draft_year) — headline score/letter grade. Doubles as
    trend-view data: filter/group by team_abbreviation_espn across draft_year.
    """
    rollup = (
        pick_grades.groupby(["team_abbreviation_espn", "draft_year"])
        .agg(
            n_picks=("pick", "size"),
            mean_rank_differential=("rank_differential", "mean"),
            mean_value_gap=("value_gap", "mean"),
            total_value_gap=("value_gap", "sum"),
        )
        .reset_index()
    )

    # Composite score: lower rank differential AND lower value gap are both
    # "better" (closer to the model's own BPA-optimal pick). z-score each
    # across all team-year rollups before averaging, since the two are on
    # very different raw scales (rank slots vs. PPS points).
    for col in ("mean_rank_differential", "mean_value_gap"):
        mean, std = rollup[col].mean(), rollup[col].std()
        rollup[f"z_{col}"] = -(rollup[col] - mean) / std if std else 0.0

    rollup["headline_score"] = (rollup["z_mean_rank_differential"] + rollup["z_mean_value_gap"]) / 2
    rollup["grade_letter"] = rollup["headline_score"].map(letter_grade_from_score)

    return rollup.sort_values(["team_abbreviation_espn", "draft_year"]).reset_index(drop=True)


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    pick_grades = build_pick_grades()
    team_rollup = build_team_rollup(pick_grades)

    write_parquet(pick_grades, "grading/pick_grades.parquet")
    write_parquet(team_rollup, "grading/team_rollup.parquet")

    return pick_grades, team_rollup


if __name__ == "__main__":
    pick_grades, team_rollup = run()

    print(f"Pick grades: {len(pick_grades)} picks")
    print(f"  mean rank differential: {pick_grades['rank_differential'].mean():.2f}")
    print(f"  mean value gap (PPS points): {pick_grades['value_gap'].mean():.2f}")
    print()

    print(f"Team rollups: {len(team_rollup)} team-year combinations")
    print(team_rollup["grade_letter"].value_counts())
    print()

    cols = [
        "team_abbreviation_espn",
        "draft_year",
        "n_picks",
        "mean_rank_differential",
        "mean_value_gap",
        "headline_score",
        "grade_letter",
    ]
    print("--- best-graded team-years ---")
    print(team_rollup.sort_values("headline_score", ascending=False).head(3)[cols])
    print()
    print("--- worst-graded team-years ---")
    print(team_rollup.sort_values("headline_score").head(3)[cols])
