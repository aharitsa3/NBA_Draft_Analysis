"""Per-player NCAA season aggregation + Phase 2.2 rate stats (design doc §4.1).

Each drafted player is represented by exactly one NCAA season: the most
recent season <= their real draft year (from the Phase 1 master draft table)
in which they have at least one played (non-DNP) game. That's their final
pre-draft season of production — the natural feature season for draft
evaluation. Confirmed against the 194 NCAA-resolved 2019-2022 picks: 191 have
a played season exactly matching their draft year; 3 don't and fall back to
their most recent prior season (Dewan Hernandez missed 2018-19 with a
suspension; Filip Petrusev skipped his would-be final NCAA season to play
overseas) or have no NCAA season at all (Shaedon Sharpe, who enrolled at
Kentucky but never played a game before declaring) — real, verified facts,
not resolution bugs. Players with no played season keep NaN features rather
than being dropped, per the missing-value-handling rule (§4.1 last bullet).

Both season_type 2 (regular) and 3 (postseason) games are included by
default in a player's target-season totals (tasks.md §2.1 recommendation);
pass season_types=(2,) to `_load_all_player_games` to exclude postseason.
The team-season context these rate stats are built against (see
features/ncaa_team_context.py) always includes both types too, for
consistency with the player side.
"""

from dataclasses import dataclass, field

import pandas as pd

from features.ncaa_team_context import build_team_season_context
from storage.paths import RAW_DATA_DIR

NCAA_SEASONS = list(range(2015, 2023))

_PLAYER_COLUMNS = [
    "athlete_id", "season", "season_type", "team_id", "did_not_play", "minutes",
    "field_goals_made", "field_goals_attempted",
    "three_point_field_goals_made", "three_point_field_goals_attempted",
    "free_throws_made", "free_throws_attempted",
    "offensive_rebounds", "defensive_rebounds", "rebounds",
    "assists", "steals", "blocks", "turnovers", "points",
    "athlete_position_abbreviation",
]

_TOTAL_COLUMNS = [
    "field_goals_made", "field_goals_attempted",
    "three_point_field_goals_made", "three_point_field_goals_attempted",
    "free_throws_made", "free_throws_attempted",
    "offensive_rebounds", "defensive_rebounds", "rebounds",
    "assists", "steals", "blocks", "turnovers", "points", "minutes",
]


@dataclass
class PlayerSeasonReport:
    n_players: int = 0
    n_resolved_season: int = 0
    no_played_season: list[str] = field(default_factory=list)


def _load_all_player_games(season_types: tuple[int, ...] = (2, 3)) -> pd.DataFrame:
    frames = []
    for season in NCAA_SEASONS:
        path = RAW_DATA_DIR / "ncaa" / "players" / f"player_box_{season}.parquet"
        frames.append(pd.read_parquet(path, columns=_PLAYER_COLUMNS))
    allp = pd.concat(frames, ignore_index=True)
    return allp[allp["season_type"].isin(season_types)]


def _pick_target_season(played_seasons: set[int], draft_year: int) -> int | None:
    eligible = [s for s in played_seasons if s <= draft_year]
    return max(eligible) if eligible else None


def _aggregate_player_season(rows: pd.DataFrame, team_ctx: pd.DataFrame) -> dict:
    played = rows[~rows["did_not_play"]]
    games_played = len(played)
    team_id = int(played["team_id"].mode().iloc[0])

    totals = played[_TOTAL_COLUMNS].sum()
    fga = totals["field_goals_attempted"]
    fgm = totals["field_goals_made"]
    fg3m = totals["three_point_field_goals_made"]
    fta = totals["free_throws_attempted"]
    tov = totals["turnovers"]
    mp = totals["minutes"]

    efg_pct = (fgm + 0.5 * fg3m) / fga if fga else None
    ft_rate = fta / fga if fga else None
    tov_pct = tov / (fga + 0.44 * fta + tov) if (fga + 0.44 * fta + tov) else None

    team_row_df = team_ctx[team_ctx["team_id"] == team_id]
    orb_pct = usage_rate = team_pace = None
    if not team_row_df.empty and mp:
        team_row = team_row_df.iloc[0]
        team_mp_equiv = team_row["team_minutes_season"] / 5
        denom_orb = mp * (team_row["team_orb_season"] + team_row["opponent_drb_season"])
        if denom_orb:
            orb_pct = 100 * totals["offensive_rebounds"] * team_mp_equiv / denom_orb
        denom_usage = mp * (
            team_row["team_fga_season"] + 0.44 * team_row["team_fta_season"] + team_row["team_tov_season"]
        )
        if denom_usage:
            usage_rate = 100 * (fga + 0.44 * fta + tov) * team_mp_equiv / denom_usage
        team_pace = team_row["team_pace"]

    return {
        "games_played": games_played,
        "minutes_total": mp,
        "minutes_per_game": mp / games_played if games_played else None,
        "ppg": totals["points"] / games_played if games_played else None,
        "rpg": totals["rebounds"] / games_played if games_played else None,
        "apg": totals["assists"] / games_played if games_played else None,
        "spg": totals["steals"] / games_played if games_played else None,
        "bpg": totals["blocks"] / games_played if games_played else None,
        "efg_pct": efg_pct,
        "ft_rate": ft_rate,
        "tov_pct": tov_pct,
        "orb_pct": orb_pct,
        "usage_rate": usage_rate,
        "team_pace": team_pace,
        "ncaa_position_abbreviation": played["athlete_position_abbreviation"].mode().iloc[0]
        if games_played
        else None,
        "ncaa_season_used": int(rows["season"].iloc[0]),
        "ncaa_team_id_used": team_id,
    }


def build_player_season_features(master: pd.DataFrame) -> tuple[pd.DataFrame, PlayerSeasonReport]:
    """master: Phase 1 master draft table rows (athlete_id_ncaa may be null)."""
    all_games = _load_all_player_games()
    games_by_athlete = {aid: g for aid, g in all_games.groupby("athlete_id")}
    team_ctx_by_season = {s: build_team_season_context(s) for s in NCAA_SEASONS}

    report = PlayerSeasonReport(n_players=len(master))
    rows = []
    for _, prow in master.iterrows():
        out = {"draft_year": prow["draft_year"], "pick": prow["pick"]}
        aid = prow["athlete_id_ncaa"]
        if pd.isna(aid):
            rows.append(out)
            continue

        aid = int(aid)
        player_games = games_by_athlete.get(aid)
        if player_games is None:
            report.no_played_season.append(prow["player_name"])
            rows.append(out)
            continue

        played_seasons = set(player_games.loc[~player_games["did_not_play"], "season"])
        target_season = _pick_target_season(played_seasons, int(prow["draft_year"]))
        if target_season is None:
            report.no_played_season.append(prow["player_name"])
            rows.append(out)
            continue

        season_rows = player_games[player_games["season"] == target_season]
        feats = _aggregate_player_season(season_rows, team_ctx_by_season[target_season])
        report.n_resolved_season += 1
        rows.append({**out, **feats})

    return pd.DataFrame(rows), report
