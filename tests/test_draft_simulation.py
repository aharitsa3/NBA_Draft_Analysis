"""§6.1 integrity constraint: the simulation's available pool at each pick must
be derived only from REAL historical selections at earlier picks — never from
what the model itself would have chosen. A buggy simulation that removed
players in BPA-ranked order (instead of real pick order) would silently
produce a hypothetical alternate draft, which is exactly what §6.1 forbids.
"""

import pandas as pd

from simulation.draft_sim import simulate_draft


def _toy_pool() -> pd.DataFrame:
    """Two 4-pick draft years where predicted_pps is deliberately inverted
    relative to real pick order (pick 4 has the highest predicted_pps) — so a
    model-driven pool would disagree with a real-history pool from pick 1
    onward. This makes the tests below non-vacuous.
    """
    rows = []
    for year in (2019, 2020):
        for pick in range(1, 5):
            rows.append(
                {
                    "draft_year": year,
                    "pick": pick,
                    "player_name": f"Player{year}_{pick}",
                    "team_abbreviation_espn": "TST",
                    "predicted_pps": float(pick),  # inverted: last real pick ranks best
                }
            )
    return pd.DataFrame(rows)


def test_pool_composition_is_real_history_not_model_driven():
    pool = _toy_pool()
    picks_df, pool_df = simulate_draft(pool)

    for year in (2019, 2020):
        for _, prow in picks_df[picks_df["draft_year"] == year].iterrows():
            pick = prow["pick"]
            actual_available = set(
                pool_df[(pool_df["draft_year"] == year) & (pool_df["pick"] == pick)]["player_name"]
            )
            # Ground truth per §6.1: everyone in the year MINUS the real
            # players picked at earlier real picks — independent of predicted_pps.
            expected_available = {f"Player{year}_{p}" for p in range(1, 5) if p >= pick}
            assert actual_available == expected_available


def test_selected_player_is_always_the_real_historical_pick():
    pool = _toy_pool()
    picks_df, _ = simulate_draft(pool)
    for _, row in picks_df.iterrows():
        assert row["player_selected"] == f"Player{row['draft_year']}_{row['pick']}"


def test_fixture_actually_exercises_model_vs_reality_divergence():
    """Guards against the above tests passing vacuously: confirms the toy
    fixture creates a case where Pure BPA's #1 choice differs from the real
    historical pick, so a model-driven-pool bug would actually be caught.
    """
    pool = _toy_pool()
    picks_df, _ = simulate_draft(pool)
    first_pick = picks_df[(picks_df["draft_year"] == 2019) & (picks_df["pick"] == 1)].iloc[0]
    assert first_pick["bpa_top_player"] != first_pick["player_selected"]
    assert first_pick["bpa_rank_of_selected"] == 4
