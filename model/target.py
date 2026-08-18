"""Target construction: Projected Production Score (design doc §2, tasks.md Phase 3).

Game Score (Hollinger) is computed per NBA player-game, averaged to a
per-player-season value ("PPS"), then the target is the mean of a drafted
player's year-2 and year-3 PPS — the two full NBA seasons immediately after
their rookie year, computed from their **real** draft year (Phase 1's master
draft table), never inferred:

    year2_season = draft_year + 2
    year3_season = draft_year + 3

(e.g. 2019 draft -> rookie season labeled 2020, year2 = 2021, year3 = 2022 —
matches tasks.md's worked example exactly.)

Only season_type 2 (regular season) and 3 (postseason) games count toward a
season's PPS — consistent with the Phase 2 NCAA aggregation policy. season_type
5 (play-in) games are excluded as a distinct, non-standard game type.

A player is only assigned a target if BOTH year2 and year3 PPS are computable
(some NBA presence, i.e. at least one played game, in each of those two
seasons). Players missing either year — never made the NBA at all, or made it
but missed/skipped one of the two target seasons — are kept in the output
table with per-year PPS filled in where available, but with
`projected_production_score` left null and a logged reason. Never silently
dropped, never imputed to a fake zero.

Field is named `projected_production_score` everywhere (never `vorp`) per
tasks.md.
"""

from dataclasses import dataclass, field

import pandas as pd

from storage.paths import RAW_DATA_DIR

NBA_SEASONS = list(range(2021, 2026))
GAME_SCORE_SEASON_TYPES = (2, 3)


@dataclass
class TargetReport:
    n_players: int = 0
    n_target_computed: int = 0
    excluded: list[tuple[str, str]] = field(default_factory=list)  # (player_name, reason)


def _compute_game_score(df: pd.DataFrame) -> pd.Series:
    return (
        df["points"]
        + 0.4 * df["field_goals_made"]
        - 0.7 * df["field_goals_attempted"]
        - 0.4 * (df["free_throws_attempted"] - df["free_throws_made"])
        + 0.7 * df["offensive_rebounds"]
        + 0.3 * df["defensive_rebounds"]
        + df["steals"]
        + 0.7 * df["assists"]
        + 0.7 * df["blocks"]
        - 0.4 * df["fouls"]
        - df["turnovers"]
    )


def _load_player_season_pps() -> pd.DataFrame:
    """One row per (athlete_id, season): mean Game Score (PPS) + games played."""
    frames = []
    for season in NBA_SEASONS:
        path = RAW_DATA_DIR / "nba" / "players" / f"player_box_{season}.parquet"
        df = pd.read_parquet(path)
        df = df[df["season_type"].isin(GAME_SCORE_SEASON_TYPES) & ~df["did_not_play"]]
        frames.append(df)
    allp = pd.concat(frames, ignore_index=True)
    allp["game_score"] = _compute_game_score(allp)
    return (
        allp.groupby(["athlete_id", "season"])
        .agg(pps=("game_score", "mean"), games_played_nba=("game_score", "size"))
        .reset_index()
    )


def build_target_table(master: pd.DataFrame) -> tuple[pd.DataFrame, TargetReport]:
    """master: Phase 1 master draft table (has real draft_year + resolved athlete_id_nba)."""
    season_pps = _load_player_season_pps()
    pps_lookup = {(row.athlete_id, row.season): (row.pps, row.games_played_nba) for row in season_pps.itertuples()}

    report = TargetReport(n_players=len(master))
    rows = []
    for _, prow in master.iterrows():
        draft_year = int(prow["draft_year"])
        year2, year3 = draft_year + 2, draft_year + 3
        aid = prow["athlete_id_nba"]

        out = {
            "draft_year": draft_year,
            "pick": prow["pick"],
            "player_name": prow["player_name"],
            "year2_season": year2,
            "year3_season": year3,
            "year2_pps": None,
            "year3_pps": None,
            "projected_production_score": None,
            "target_excluded_reason": None,
        }

        if pd.isna(aid):
            reason = "no resolved NBA box-score player (Phase 1) — never appeared in the NBA data window"
            out["target_excluded_reason"] = reason
            report.excluded.append((prow["player_name"], reason))
            rows.append(out)
            continue

        aid = int(aid)
        y2 = pps_lookup.get((aid, year2))
        y3 = pps_lookup.get((aid, year3))
        out["year2_pps"] = y2[0] if y2 else None
        out["year3_pps"] = y3[0] if y3 else None

        if y2 and y3:
            out["projected_production_score"] = (y2[0] + y3[0]) / 2
            report.n_target_computed += 1
        else:
            missing = []
            if not y2:
                missing.append(f"year 2 ({year2})")
            if not y3:
                missing.append(f"year 3 ({year3})")
            reason = f"no NBA box-score games in {' or '.join(missing)}"
            out["target_excluded_reason"] = reason
            report.excluded.append((prow["player_name"], reason))

        rows.append(out)

    return pd.DataFrame(rows), report
