"""Phase 3 driver: build the Projected Production Score target table, persist it,
and fold the real target into Phase 2's training table (replacing its
placeholder `projected_production_score` column).

Persists:
  - processed_data/model/target_table.parquet — per-player year2/year3 PPS,
    final target, and exclusion reasons (never silently dropped)
  - processed_data/features/training_table.parquet — updated in place with the
    real target column

Run with: python -m model.build_target
"""

import pandas as pd

from model.target import build_target_table
from storage.io import read_parquet, write_parquet


def run() -> pd.DataFrame:
    master = read_parquet("identity/master_draft_table.parquet")
    target_table, report = build_target_table(master)
    write_parquet(target_table, "model/target_table.parquet")

    training_table = read_parquet("features/training_table.parquet")
    training_table = training_table.drop(columns=["projected_production_score"]).merge(
        target_table[
            [
                "draft_year",
                "pick",
                "year2_pps",
                "year3_pps",
                "projected_production_score",
                "target_excluded_reason",
            ]
        ],
        on=["draft_year", "pick"],
        how="left",
    )
    write_parquet(training_table, "features/training_table.parquet")

    n = report.n_players
    print(f"Target table: {n} real picks, 2019-2022")
    print(f"  projected_production_score computed: {report.n_target_computed}/{n} ({report.n_target_computed / n:.1%})")
    print(f"  excluded: {len(report.excluded)}")
    print()

    print("--- target distribution (computed only) ---")
    print(target_table["projected_production_score"].describe())
    print()

    print("--- exclusion reasons (grouped) ---")
    reasons = pd.Series([r for _, r in report.excluded]).value_counts()
    print(reasons)
    print()

    print("--- exclusions by draft year ---")
    excluded_names = {name for name, _ in report.excluded}
    excl_df = target_table[target_table["player_name"].isin(excluded_names)]
    print(excl_df.groupby("draft_year").size())
    print()

    print("--- spot checks (well-known players, real career outcomes) ---")
    for name in ["Zion Williamson", "Ja Morant"]:
        row = target_table[target_table["player_name"] == name]
        if not row.empty:
            r = row.iloc[0]
            print(f"  {name}: year2_pps={r['year2_pps']}, year3_pps={r['year3_pps']}, "
                  f"pps={r['projected_production_score']}")

    return training_table


if __name__ == "__main__":
    run()
