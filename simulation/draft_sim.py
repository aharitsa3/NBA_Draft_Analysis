"""Sequential draft simulation — Pure BPA ranking (design doc §6.1, §6.2.1).

Walks the REAL historical draft order (Phase 1 master draft table, `pick`
1->N per year, `order.csv`-verified) and at each pick ranks the remaining
player pool by predicted PPS (Phase 4's model).

**Integrity constraint (§6.1):** the available pool at pick i is defined
ONLY by which real players were actually selected at picks 1..i-1 — never by
what the model itself would have picked. The simulation never builds a
hypothetical alternate board off its own prior choices; it only ever asks
"given who's really gone by now, who does the model like best of what's
left." See tests/test_draft_simulation.py for an explicit test of this.

Run with: python -m simulation.draft_sim
"""

import pandas as pd

from storage.io import read_parquet, write_parquet


def load_draft_pool() -> pd.DataFrame:
    master = read_parquet("identity/master_draft_table.parquet")
    preds = read_parquet("model/predictions.parquet")
    df = master.merge(preds[["draft_year", "pick", "predicted_pps"]], on=["draft_year", "pick"], how="left")
    return df.sort_values(["draft_year", "pick"]).reset_index(drop=True)


def simulate_draft(pool: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """pool: one row per real pick (draft_year, pick, player_name, team_abbreviation_espn,
    predicted_pps). Returns (picks_df, available_pool_df).
    """
    pick_rows = []
    pool_rows = []

    for year, year_df in pool.groupby("draft_year"):
        year_df = year_df.sort_values("pick").reset_index(drop=True)

        # The only state this loop carries across iterations is which REAL
        # picks (by pick number) have already happened — never a model output.
        already_selected_picks: set[int] = set()

        for _, row in year_df.iterrows():
            current_pick = int(row["pick"])

            available = year_df[~year_df["pick"].isin(already_selected_picks)].copy()
            available = available.sort_values("predicted_pps", ascending=False).reset_index(drop=True)
            available["rank_in_pool"] = available.index + 1

            for _, arow in available.iterrows():
                pool_rows.append(
                    {
                        "draft_year": year,
                        "pick": current_pick,
                        "rank_in_pool": int(arow["rank_in_pool"]),
                        "player_name": arow["player_name"],
                        "predicted_pps": arow["predicted_pps"],
                    }
                )

            selected_row = available[available["pick"] == current_pick].iloc[0]
            bpa_top = available.iloc[0]

            pick_rows.append(
                {
                    "draft_year": year,
                    "pick": current_pick,
                    "team_abbreviation_espn": row["team_abbreviation_espn"],
                    "player_selected": row["player_name"],
                    "predicted_pps_selected": row["predicted_pps"],
                    "bpa_rank_of_selected": int(selected_row["rank_in_pool"]),
                    "bpa_top_player": bpa_top["player_name"],
                    "bpa_top_predicted_pps": bpa_top["predicted_pps"],
                    "pool_size": len(available),
                }
            )

            # Advance real history by exactly one real pick — nothing model-driven.
            already_selected_picks.add(current_pick)

    return pd.DataFrame(pick_rows), pd.DataFrame(pool_rows)


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    pool = load_draft_pool()
    picks_df, pool_df = simulate_draft(pool)
    write_parquet(picks_df, "simulation/picks.parquet")
    write_parquet(pool_df, "simulation/available_pool.parquet")
    return picks_df, pool_df


if __name__ == "__main__":
    picks_df, pool_df = run()

    print(f"Simulated {len(picks_df)} picks across {picks_df['draft_year'].nunique()} draft years")
    print(picks_df.groupby("draft_year").size())
    print()

    n_bpa_matches = (picks_df["bpa_rank_of_selected"] == 1).sum()
    print(f"Real picks that matched Pure BPA's #1 available player: {n_bpa_matches}/{len(picks_df)}")
    print(f"Mean BPA rank of the real pick: {picks_df['bpa_rank_of_selected'].mean():.2f}")
    print()

    print("--- spot check: 2019 pick 1 (Zion Williamson) ---")
    row = picks_df[(picks_df["draft_year"] == 2019) & (picks_df["pick"] == 1)].iloc[0]
    print(row[["player_selected", "predicted_pps_selected", "bpa_top_player", "bpa_rank_of_selected", "pool_size"]])
