"""Team-season context needed as ORB%/Usage-Rate/pace denominators (tasks.md §2.1/§2.2).

No explicit team-minutes or possessions column exists in `data/ncaa/teams` —
both are derived here: team minutes from summed player minutes per team-game,
possessions/pace from the team's own box totals.
"""

import pandas as pd

from storage.paths import RAW_DATA_DIR

NCAA_SEASONS = list(range(2015, 2023))


def _load_team_box(season: int) -> pd.DataFrame:
    path = RAW_DATA_DIR / "ncaa" / "teams" / f"team_box_{season}.parquet"
    return pd.read_parquet(path)


def _load_team_minutes(season: int) -> pd.DataFrame:
    """Sum player minutes per (game_id, team_id) — the team-minutes proxy."""
    path = RAW_DATA_DIR / "ncaa" / "players" / f"player_box_{season}.parquet"
    df = pd.read_parquet(path, columns=["game_id", "team_id", "minutes", "did_not_play"])
    df = df[~df["did_not_play"]]
    return df.groupby(["game_id", "team_id"])["minutes"].sum().rename("team_minutes").reset_index()


def build_team_game_context(season: int) -> pd.DataFrame:
    """One row per (game_id, team_id): own FGA/FTA/TOV/ORB, opponent's DRB, team minutes, possessions."""
    tb = _load_team_box(season)
    minutes = _load_team_minutes(season)
    tb = tb.merge(minutes, on=["game_id", "team_id"], how="left")

    # team_box's own "opponent_*" columns only carry score, not full stats — self-join
    # to pull the opponent's own defensive_rebounds row for the same game.
    opp_drb = tb[["game_id", "team_id", "defensive_rebounds"]].rename(
        columns={"team_id": "opponent_team_id", "defensive_rebounds": "opponent_defensive_rebounds"}
    )
    tb = tb.merge(opp_drb, on=["game_id", "opponent_team_id"], how="left")

    tb["possessions"] = (
        tb["field_goals_attempted"]
        - tb["offensive_rebounds"]
        + tb["turnovers"]
        + 0.44 * tb["free_throws_attempted"]
    )
    return tb


def build_team_season_context(season: int) -> pd.DataFrame:
    """One row per team_id: season totals used as ORB%/Usage-Rate denominators + season pace.

    Team_MP/Team_ORB/Team_FGA/etc. are the team's totals across ALL of its games
    that season (not just games a given player appeared in) — this matches the
    standard Basketball-Reference definition of these rate stats.
    """
    game_ctx = build_team_game_context(season)
    agg = (
        game_ctx.groupby("team_id")
        .agg(
            team_minutes_season=("team_minutes", "sum"),
            team_fga_season=("field_goals_attempted", "sum"),
            team_fta_season=("free_throws_attempted", "sum"),
            team_tov_season=("turnovers", "sum"),
            team_orb_season=("offensive_rebounds", "sum"),
            opponent_drb_season=("opponent_defensive_rebounds", "sum"),
            team_pace=("possessions", "mean"),
            team_games=("game_id", "nunique"),
        )
        .reset_index()
    )
    agg["season"] = season
    return agg
