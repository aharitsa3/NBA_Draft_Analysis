"""Resolve each drafted player (master draft table, Phase 1) to their `athlete_id`
in the NCAA and NBA box score files, by normalized name — never by `athlete_id`,
since picks/order/NCAA/NBA are confirmed to use different id namespaces.

Common-name collisions (multiple distinct real people sharing a normalized name,
e.g. two different "Cameron Johnson"s across different schools) are resolved
using the drafted player's college (`college_order`, carried through from
`order.csv` — see draft_join.py) matched against the NCAA team's school name
(`team_location`). A small number of college names appear abbreviated in
`order.csv` relative to how the school is named in `team_location`; those are
expanded here. Verified against real data: of 19 drafted-player names that
collide in the NCAA data (2019-2022 draft classes), college-based disambiguation
resolves 19/19 once "UNC" -> "North Carolina" is added.

The NBA side has zero name collisions among 2019-2022 draftees (checked against
`data/nba/players` 2021-2025), so no disambiguation is needed there.
"""

from dataclasses import dataclass, field

import pandas as pd

from identity.name_normalize import normalize_name
from storage.paths import RAW_DATA_DIR

# order.csv college names that don't literally appear as a substring of the
# NCAA `team_location` value for that school — expand before substring-matching.
COLLEGE_ABBREVIATION_EXPANSIONS: dict[str, str] = {
    "unc": "north carolina",
}

# The master table's join_name is order.csv's own spelling (or the picks<->order
# override target — see name_overrides.py), which is the right canonical key for
# that join but is occasionally NOT how NCAA/NBA box scores spell the same
# player (verified case: order.csv lists "Xavier Tillman Sr.", but both
# `data/ncaa/players` and `data/nba/players` list him as plain "Xavier Tillman").
# Tried as a fallback only when the primary join_name has no match.
BOX_SCORE_NAME_ALIASES: dict[str, str] = {
    "xavier tillman sr": "xavier tillman",
    "brandon boston jr": "brandon boston",
}


@dataclass
class BoxScoreJoinReport:
    source: str  # "ncaa" or "nba"
    n_players: int = 0
    n_resolved_unique: int = 0
    n_resolved_via_college: int = 0
    unresolved: list[str] = field(default_factory=list)  # (name, reason)
    unresolved_reasons: dict[str, str] = field(default_factory=dict)


def _load_distinct_players(paths: list) -> pd.DataFrame:
    frames = []
    for path in paths:
        cols = ["athlete_id", "athlete_display_name"]
        if "ncaa" in str(path):
            cols.append("team_location")
        df = pd.read_parquet(path, columns=cols)
        frames.append(df.drop_duplicates())
    allp = pd.concat(frames, ignore_index=True).drop_duplicates()
    allp["join_name"] = allp["athlete_display_name"].map(normalize_name)
    return allp


def _resolve_source(
    master: pd.DataFrame, box_players: pd.DataFrame, source: str
) -> tuple[pd.DataFrame, BoxScoreJoinReport]:
    has_college = "team_location" in box_players.columns
    report = BoxScoreJoinReport(source=source, n_players=len(master))

    by_name: dict[str, pd.DataFrame] = {
        name: g for name, g in box_players.groupby("join_name")
    }

    resolved_ids = []
    resolution_reasons = []
    for _, prow in master.iterrows():
        name_key = prow["join_name"]
        candidates = by_name.get(name_key)
        if (candidates is None or candidates.empty) and name_key in BOX_SCORE_NAME_ALIASES:
            name_key = BOX_SCORE_NAME_ALIASES[name_key]
            candidates = by_name.get(name_key)

        if candidates is None or candidates.empty:
            resolved_ids.append(None)
            resolution_reasons.append("not_found")
            reason = f"no {source} record found for name '{prow['player_name']}'"
            report.unresolved.append(prow["player_name"])
            report.unresolved_reasons[prow["player_name"]] = reason
            continue

        distinct_ids = candidates["athlete_id"].unique()
        if len(distinct_ids) == 1:
            resolved_ids.append(distinct_ids[0])
            resolution_reasons.append("unique")
            report.n_resolved_unique += 1
            continue

        if has_college and pd.notna(prow.get("college_order")):
            college_norm = normalize_name(prow["college_order"])
            college_norm = COLLEGE_ABBREVIATION_EXPANSIONS.get(college_norm, college_norm)
            id_to_locations = candidates.groupby("athlete_id")["team_location"].apply(
                lambda s: {normalize_name(x) for x in s.dropna()}
            )
            matches = [
                aid
                for aid, locs in id_to_locations.items()
                if any(loc in college_norm or college_norm in loc for loc in locs)
            ]
            if len(matches) == 1:
                resolved_ids.append(matches[0])
                resolution_reasons.append("disambiguated_via_college")
                report.n_resolved_via_college += 1
                continue

        resolved_ids.append(None)
        resolution_reasons.append("ambiguous")
        reason = (
            f"name '{prow['player_name']}' matches {len(distinct_ids)} distinct "
            f"{source} players and college-based disambiguation did not resolve to one"
        )
        report.unresolved.append(prow["player_name"])
        report.unresolved_reasons[prow["player_name"]] = reason

    out = master.copy()
    out[f"athlete_id_{source}"] = resolved_ids
    out[f"{source}_resolution"] = resolution_reasons
    return out, report


def resolve_ncaa(master: pd.DataFrame) -> tuple[pd.DataFrame, BoxScoreJoinReport]:
    paths = sorted((RAW_DATA_DIR / "ncaa" / "players").glob("player_box_*.parquet"))
    box_players = _load_distinct_players(paths)
    return _resolve_source(master, box_players, "ncaa")


def resolve_nba(master: pd.DataFrame) -> tuple[pd.DataFrame, BoxScoreJoinReport]:
    paths = sorted((RAW_DATA_DIR / "nba" / "players").glob("player_box_*.parquet"))
    box_players = _load_distinct_players(paths)
    return _resolve_source(master, box_players, "nba")
