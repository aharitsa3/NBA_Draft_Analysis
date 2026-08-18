"""Assemble the Phase 2 training table: one row per drafted player (2019-2022)
with all design-doc §4.1 features + a placeholder for the Phase 3 target.

Only §4.1 features are built here — §4.2's explicit exclusion list (age/class
year, wingspan, combine testing, conference, strength-of-schedule, real
advanced metrics as inputs) is intentionally not sourced anywhere in this
pipeline; nothing downstream should reference those.

Run with: python -m features.build_training_table
"""

import pandas as pd

from features.ncaa_player_season import build_player_season_features
from features.position import position_bucket
from features.trajectory import build_years_of_data_available
from storage.io import read_parquet, write_parquet

FEATURE_COLUMNS = [
    "draft_year",
    "pick",
    "player_name",
    "team_abbreviation_espn",
    "athlete_id_ncaa",
    "athlete_id_nba",
    "games_played",
    "minutes_total",
    "minutes_per_game",
    "ppg",
    "rpg",
    "apg",
    "spg",
    "bpg",
    "efg_pct",
    "ft_rate",
    "tov_pct",
    "orb_pct",
    "usage_rate",
    "team_pace",
    "years_of_college_data_available",
    "position_bucket",
    "athlete_height",
    "athlete_weight",
    "ncaa_season_used",
    "ncaa_team_id_used",
]


def build_training_table() -> tuple[pd.DataFrame, dict]:
    master = read_parquet("identity/master_draft_table.parquet")

    season_feats, season_report = build_player_season_features(master)
    years_avail = build_years_of_data_available()

    table = master.merge(season_feats, on=["draft_year", "pick"], how="left")

    table["years_of_college_data_available"] = table["athlete_id_ncaa"].map(years_avail)

    # Position bucket prefers the player's target-season NCAA label (design doc
    # §4.1); falls back to the picks.parquet bio position (already resolved in
    # the master table) only when no NCAA season exists at all (e.g. Shaedon
    # Sharpe, who never played a game before declaring).
    ncaa_bucket = table["ncaa_position_abbreviation"].map(position_bucket)
    bio_bucket = table["athlete_position_abbreviation"].map(position_bucket)
    table["position_bucket"] = ncaa_bucket.where(ncaa_bucket != "UNK", bio_bucket)

    table = table[FEATURE_COLUMNS].copy()
    table["projected_production_score"] = pd.NA  # Phase 3 fills this in

    no_data_rows = pd.DataFrame(
        {
            "player_name": season_report.no_played_season,
            "reason": "no NCAA season with a played game found at/before the player's real draft year",
        }
    )

    write_parquet(table, "features/training_table.parquet")
    write_parquet(no_data_rows, "features/no_ncaa_season_players.parquet")

    return table, {
        "n_players": season_report.n_players,
        "n_resolved_season": season_report.n_resolved_season,
        "no_played_season": season_report.no_played_season,
    }


if __name__ == "__main__":
    table, summary = build_training_table()

    print(f"Training table: {len(table)} rows (drafted players, 2019-2022)")
    print(f"  NCAA season resolved: {summary['n_resolved_season']}/{summary['n_players']}")
    print(f"  no NCAA season found: {len(summary['no_played_season'])} -> {summary['no_played_season']}")
    print()

    print("--- feature completeness (non-null %) ---")
    for col in FEATURE_COLUMNS:
        pct = table[col].notna().mean()
        print(f"  {col}: {pct:.1%}")
    print()

    print("--- position bucket distribution ---")
    print(table["position_bucket"].value_counts(dropna=False))
    print()

    print("--- spot check: Zion Williamson (2019 pick 1) ---")
    row = table[(table["draft_year"] == 2019) & (table["pick"] == 1)]
    if not row.empty:
        print(row.iloc[0][["player_name", "ppg", "rpg", "efg_pct", "usage_rate", "ncaa_season_used"]])
