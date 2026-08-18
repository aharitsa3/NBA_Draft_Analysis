"""Feature matrix prep for model training (design doc §4.1) — shared between
CV, final-fit, and inference so the exact same columns are built every time.

Model inputs are restricted to §4.1's feature list only (no draft_year, pick,
team, or raw NCAA/NBA IDs — those are identifiers/metadata, not predictive
features, and including the real drafting team in particular would leak
historical-outcome information into what's supposed to be a pre-draft talent
evaluation). Both XGBoost and this project's sklearn version (1.9, verified)
handle NaN natively in tree splits, so missing feature values are passed
through as-is rather than imputed — matching the design doc's stated
missing-value policy.
"""

import pandas as pd

NUMERIC_FEATURE_COLUMNS = [
    "efg_pct",
    "ft_rate",
    "tov_pct",
    "orb_pct",
    "usage_rate",
    "ppg",
    "rpg",
    "apg",
    "spg",
    "bpg",
    "minutes_per_game",
    "team_pace",
    "years_of_college_data_available",
    "athlete_height",
    "athlete_weight",
]

POSITION_CATEGORIES = ["C", "F", "G", "UNK"]

FEATURE_ENCODER = {
    "numeric_feature_columns": NUMERIC_FEATURE_COLUMNS,
    "position_categories": POSITION_CATEGORIES,
}


def build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """df must have NUMERIC_FEATURE_COLUMNS + `position_bucket`. Returns a numeric
    matrix: the numeric columns as-is (NaN preserved) + one-hot position columns.
    """
    X = df[NUMERIC_FEATURE_COLUMNS].astype(float).copy()
    for category in POSITION_CATEGORIES:
        X[f"position_{category}"] = (df["position_bucket"] == category).astype(float)
    return X
