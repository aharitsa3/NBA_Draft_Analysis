"""Join `data/nba/draft/picks` <-> `data/nba/draft/order` per draft year to build
the master draft table (§3.5 / Phase 1).

`order.csv`'s `Pk`/`Tm` are authoritative (verified against real draft history);
`picks.parquet`'s `pick`/`overall_pick`/`round`/`team_id` are not used at all.
The join key is normalized player name (+ manual overrides for nickname/legal-name
variants), never `athlete_id` (confirmed different namespace between the two files).

Every real pick (an `order.csv` row with a non-null `Pk`) becomes exactly one row
in the master table, even if no bio match is found in `picks.parquet` — those rows
just carry NaN bio fields and a logged reason, per the "don't silently drop
unmatched players" requirement in tasks.md Phase 1.
"""

from dataclasses import dataclass, field

import pandas as pd

from identity.measurements import parse_height_inches, parse_weight_lbs
from identity.name_normalize import normalize_name
from identity.name_overrides import PICKS_TO_ORDER_NAME_OVERRIDES
from identity.team_mapping import BREF_TO_ESPN_TEAM_ABBR
from storage.paths import RAW_DATA_DIR

DRAFT_YEARS = [2019, 2020, 2021, 2022]


@dataclass
class JoinReport:
    """Human-readable record of what matched and what didn't, per draft year."""

    year: int
    n_order_picks: int = 0
    n_bio_matched: int = 0
    unmatched_order_names: list[str] = field(default_factory=list)  # no bio found
    unmatched_picks_names: list[str] = field(default_factory=list)  # not a real pick
    collision_names: list[str] = field(default_factory=list)  # same join_name, >1 row on one side


def _load_order(year: int) -> pd.DataFrame:
    path = RAW_DATA_DIR / "nba" / "draft" / "order" / f"order_{year}.csv"
    df = pd.read_csv(path, header=1)
    df = df[df["Pk"].notna()].copy()
    df["Pk"] = df["Pk"].astype(int)
    df["join_name"] = df["Player"].map(normalize_name)
    return df


def _load_picks(year: int) -> pd.DataFrame:
    path = RAW_DATA_DIR / "nba" / "draft" / "picks" / f"draft_{year}.parquet"
    df = pd.read_parquet(path)
    df["join_name"] = df["athlete_display_name"].map(normalize_name)
    df["join_name"] = df["join_name"].map(lambda n: PICKS_TO_ORDER_NAME_OVERRIDES.get(n, n))
    return df


def build_master_draft_table() -> tuple[pd.DataFrame, list[JoinReport]]:
    rows = []
    reports = []

    for year in DRAFT_YEARS:
        order = _load_order(year)
        picks = _load_picks(year)

        picks_by_name: dict[str, list[dict]] = {}
        for _, prow in picks.iterrows():
            picks_by_name.setdefault(prow["join_name"], []).append(prow.to_dict())

        matched_picks_names: set[str] = set()
        report = JoinReport(year=year, n_order_picks=len(order))

        for name_key, candidates in picks_by_name.items():
            if len(candidates) > 1:
                report.collision_names.append(
                    f"{name_key} ({len(candidates)} picks.parquet rows)"
                )
        dup_order_names = order["join_name"][order["join_name"].duplicated(keep=False)]
        for name_key in sorted(set(dup_order_names)):
            report.collision_names.append(f"{name_key} ({(dup_order_names == name_key).sum()} order.csv rows)")

        for _, orow in order.iterrows():
            name_key = orow["join_name"]
            bio_candidates = picks_by_name.get(name_key, [])

            if len(bio_candidates) >= 1:
                bio = bio_candidates[0]
                matched_picks_names.add(name_key)
                report.n_bio_matched += 1
                player_name = bio["athlete_display_name"]
                bio_matched = True
            else:
                bio = {}
                player_name = orow["Player"]
                bio_matched = False
                report.unmatched_order_names.append(orow["Player"])

            team_bref = orow["Tm"]
            rows.append(
                {
                    "draft_year": year,
                    "pick": orow["Pk"],
                    "team_abbreviation_bref": team_bref,
                    "team_abbreviation_espn": BREF_TO_ESPN_TEAM_ABBR.get(team_bref),
                    "player_name": player_name,
                    "join_name": name_key,
                    "athlete_id_picks": bio.get("athlete_id"),
                    "athlete_height": parse_height_inches(bio.get("athlete_height")),
                    "athlete_weight": parse_weight_lbs(bio.get("athlete_weight")),
                    "athlete_position_abbreviation": bio.get("athlete_position_abbreviation"),
                    "bio_matched": bio_matched,
                    # From order.csv, kept only to help disambiguate name collisions when
                    # joining to NCAA box scores (identity/box_score_join.py) — not a model
                    # feature (§4.2 excludes conference/college as inputs).
                    "college_order": orow.get("College"),
                }
            )

        for name_key, candidates in picks_by_name.items():
            if name_key not in matched_picks_names:
                for c in candidates:
                    report.unmatched_picks_names.append(c["athlete_display_name"])

        reports.append(report)

    master = pd.DataFrame(rows)
    return master, reports


def reports_to_frame(reports: list[JoinReport]) -> pd.DataFrame:
    """Flatten JoinReports into one row per (year, unmatched-name, side) for persistence."""
    rows = []
    for r in reports:
        for name in r.unmatched_order_names:
            rows.append(
                {
                    "draft_year": r.year,
                    "name": name,
                    "side": "order_only",
                    "reason": "no bio match found in picks.parquet (name, height, weight, "
                    "position will be missing for this real pick)",
                }
            )
        for name in r.unmatched_picks_names:
            rows.append(
                {
                    "draft_year": r.year,
                    "name": name,
                    "side": "picks_only",
                    "reason": "not present in the verified real draft order (order.csv) for "
                    "this year — excluded from the master draft table",
                }
            )
        for name in r.collision_names:
            rows.append(
                {
                    "draft_year": r.year,
                    "name": name,
                    "side": "collision",
                    "reason": "multiple rows share this normalized name within the year",
                }
            )
    return pd.DataFrame(rows)
