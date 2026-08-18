"""Phase 1 validation script (tasks.md §Phase 1, final bullet).

Runs the full identity-resolution pipeline (picks<->order join, then NCAA and
NBA box-score resolution) and reports:
  - % of picks successfully resolved to an NCAA player
  - % resolved to NBA (year-2/3 presence is Phase 3's job; this just confirms
    the player has *any* NBA box-score row, i.e. the athlete_id resolved)
  - every pick that fails either join, with a logged reason (never silently
    dropped — they remain in the master table, just with a null athlete_id
    for whichever source didn't resolve)

Persists:
  - processed_data/identity/master_draft_table.parquet — one row per real pick,
    2019-2022, with athlete_id_ncaa / athlete_id_nba resolved where possible
  - processed_data/identity/draft_join_report.parquet — picks<->order unmatched
    names/collisions
  - processed_data/identity/box_score_unresolved.parquet — per-player NCAA/NBA
    resolution failures with reasons

Run with: python -m identity.validate
"""

import pandas as pd

from identity.box_score_join import resolve_nba, resolve_ncaa
from identity.draft_join import build_master_draft_table, reports_to_frame
from storage.io import write_parquet

KNOWN_PICK_SPOT_CHECKS = [
    (2019, 1, "Zion Williamson"),
    (2019, 2, "Ja Morant"),
]


def run() -> pd.DataFrame:
    master, join_reports = build_master_draft_table()
    master_ncaa, ncaa_report = resolve_ncaa(master)
    master_full, nba_report = resolve_nba(master_ncaa)

    write_parquet(master_full, "identity/master_draft_table.parquet")
    write_parquet(reports_to_frame(join_reports), "identity/draft_join_report.parquet")

    unresolved_rows = []
    for report in (ncaa_report, nba_report):
        for name, reason in report.unresolved_reasons.items():
            unresolved_rows.append({"source": report.source, "player_name": name, "reason": reason})
    write_parquet(pd.DataFrame(unresolved_rows), "identity/box_score_unresolved.parquet")

    n = len(master_full)
    n_bio = int(master_full["bio_matched"].sum())
    n_ncaa = int(master_full["athlete_id_ncaa"].notna().sum())
    n_nba = int(master_full["athlete_id_nba"].notna().sum())

    print(f"Master draft table: {n} real picks, 2019-2022")
    print(f"  bio (picks.parquet) matched:  {n_bio}/{n} ({n_bio / n:.1%})")
    print(f"  NCAA athlete_id resolved:     {n_ncaa}/{n} ({n_ncaa / n:.1%})")
    print(f"  NBA athlete_id resolved:      {n_nba}/{n} ({n_nba / n:.1%})")
    print()

    print("--- picks<->order join, per year ---")
    for r in join_reports:
        print(
            f"  {r.year}: {r.n_bio_matched}/{r.n_order_picks} bio-matched; "
            f"{len(r.unmatched_order_names)} order-only (missing bio), "
            f"{len(r.unmatched_picks_names)} picks-only (excluded, not a real pick)"
        )
    print()

    print(f"--- NCAA resolution failures ({len(ncaa_report.unresolved)}) ---")
    for name in ncaa_report.unresolved:
        print(f"  {name}: {ncaa_report.unresolved_reasons[name]}")
    print()

    print(f"--- NBA resolution failures ({len(nba_report.unresolved)}) ---")
    for name in nba_report.unresolved:
        print(f"  {name}: {nba_report.unresolved_reasons[name]}")
    print()

    print("--- spot checks ---")
    for year, pick, expected_name in KNOWN_PICK_SPOT_CHECKS:
        row = master_full[(master_full["draft_year"] == year) & (master_full["pick"] == pick)]
        if row.empty:
            print(f"  FAIL: {year} pick {pick} not found in master table")
            continue
        row = row.iloc[0]
        ok_name = row["player_name"] == expected_name
        ok_ncaa = pd.notna(row["athlete_id_ncaa"])
        ok_nba = pd.notna(row["athlete_id_nba"])
        status = "OK" if (ok_name and ok_ncaa and ok_nba) else "CHECK"
        print(
            f"  [{status}] {year} pick {pick}: expected '{expected_name}', got "
            f"'{row['player_name']}' (ncaa id={row['athlete_id_ncaa']}, "
            f"nba id={row['athlete_id_nba']})"
        )

    return master_full


if __name__ == "__main__":
    run()
