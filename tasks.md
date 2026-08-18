# NBA Draft Analysis — Implementation Tasks

Derived from `nba_draft_analysis_design_doc.md` (v2). Section references (§) point back to the design doc. All data is already local in `data/` — there is no fetch/scrape stage anywhere in this plan, and nothing here should assume data that isn't already verified present.

## Verified Data Inventory

| Path | Coverage | Grain | Key verified facts |
|---|---|---|---|
| `data/ncaa/players/player_box_*.parquet` | 2015–2022 (label = season-end year) | player-game | Full box score cols + position + `team_id`. No height/weight/conference. |
| `data/ncaa/teams/team_box_*.parquet` | 2015–2022 | team-game | Team box cols; `team_id` joins 1:1 to player file. No possessions/pace column. |
| `data/nba/players/player_box_*.parquet` | 2021–2025 | player-game | Same shape as NCAA + `plus_minus`. No advanced metrics. No `nba/teams` folder exists. |
| `data/nba/draft/picks/draft_*.parquet` | 2019–2022, 60 rows/yr | one row per pick | `athlete_display_name`, `athlete_height`/`athlete_weight` (100% populated), position. **`pick`/`overall_pick`/`round`/`team_id` are unreliable — do not use.** `athlete_id` is a different namespace than box-score `athlete_id`. `college_name` is 100% null. |
| `data/nba/draft/order/order_*.csv` | 2019–2022, 60 rows/yr | one row per pick | `Pk`/`Tm` verified correct against real draft history — **use only these two columns.** `WS`/`BPM`/`VORP`/per-game/career-total columns exist but are explicitly excluded (career totals, not year-2/3-specific). |

---

## Phase 0 — Project Setup

- [x] Initialize git repo, `.gitignore` (processed outputs, *.pkl, .env, __pycache__) — keep `data/` tracked as-is
- [x] Project structure: `identity/` (join logic), `features/`, `model/`, `simulation/`, `grading/`, `dashboard/`, `reports/`, `storage/`, `tests/`
- [x] Dependencies: `pandas`, `pyarrow`, `xgboost`, `lightgbm`, `scikit-learn`, `streamlit`, `anthropic`. No scraping libs needed — nothing is fetched.
- [x] `storage/` module with read/write helpers for processed Parquet outputs, written to a path separate from raw `data/`
- [x] `.env` handling for Anthropic API key (needed later for Phase 9)

---

## Phase 1 — Identity Resolution & Join Strategy (§3.5, §10)

This is flagged in the design doc as the single highest-risk step — a bad match silently corrupts a player's entire row. Build and hand-verify before anything downstream depends on it.

- [x] Build player-name normalization function (strip periods, collapse whitespace, transliterate diacritics e.g. `Šamanić`→`Samanic`, handle common nickname/legal-name variants) — apply consistently everywhere a name is used as a join key
- [x] Join `data/nba/draft/picks` ↔ `data/nba/draft/order` by normalized name, within each draft year — expect ~70-75% exact match rate pre-normalization (verified: 44/60 in 2019); after normalization, generate a report of remaining unmatched pairs per year
- [x] Manually resolve remaining unmatched pairs (small: ~15-20 players/year × 4 years) — hand-correct in a small override/lookup table, don't silently drop unmatched players
- [x] Build the resulting **master draft table**: one row per pick, 2019-2022, all rounds — `Pk` and `Tm` from `order.csv` (authoritative), name/height/weight/position from `picks.parquet` (bio only — never pull `pick`/`round`/`team_id` from this file)
- [x] Join master draft table players ↔ NCAA box score players by normalized name (not `athlete_id` — confirmed different namespace) — generate an unmatched-name report, spot-check for common-name collisions (multiple distinct NCAA players sharing a display name), hand-resolve
- [x] Join master draft table players ↔ NBA box score players by normalized name, same process
- [x] Build static BRef→ESPN team abbreviation mapping table (~30 rows, e.g. `PHO`→`PHX`, `BRK`→`BKN`, `CHO`→`CHA`) — hand-built, verify against all 30 teams before use
- [x] Write a single validation script that reports: % of picks successfully resolved to an NCAA player, % resolved to NBA year-2/3 data, list of any picks that fail either join (these players must be excluded from training with a logged reason, not silently dropped)

---

## Phase 2 — Season Aggregation & Feature Engineering (§4.1)

Box score files are game-level — aggregation to one-row-per-player-per-season is a prerequisite.

### 2.1 Aggregation
- [x] Aggregate NCAA player game logs to season totals + per-game averages, per resolved player + season
- [x] Build team-game aggregates (join player rows to `data/ncaa/teams` on `team_id`+`game_id`, and to the opponent's row via `opponent_team_id`+`game_id`) — needed for ORB%/usage% denominators
- [x] Decide `season_type` handling (2=regular, 3=postseason) — recommend including both, but keep the flag available to exclude postseason if it skews small-sample players

### 2.2 Features — build only these (§4.1); do not add anything from §4.2
- [x] eFG% = (FGM + 0.5·3PM) / FGA
- [x] FT Rate = FTA/FGA (or FTM/FGA)
- [x] TOV% (individual) = TOV / (FGA + 0.44·FTA + TOV)
- [x] ORB% = `100 · ORB · (Team_MP/5) / (MP · (Team_ORB + Opp_DRB))` using the team-game join from 2.1
- [x] Usage Rate = `100 · (FGA + 0.44·FTA + TOV) · (Team_MP/5) / (MP · (Team_FGA + 0.44·Team_FTA + Team_TOV))` — derive Team_MP from summed player minutes per team-game (no explicit team-minutes column exists)
- [x] PPG, RPG, APG, SPG, BPG, minutes played
- [x] Team pace/possessions: `Poss ≈ FGA − ORB + TOV + 0.44·FTA`, from `data/ncaa/teams`, per team-season
- [x] Years-of-college-data-available (trajectory proxy): count of distinct NCAA seasons a player appears in, 2015–2022 — document the left-censoring caveat (career start before 2015 undercounts) directly in code comments/README, not just this doc
- [x] Position bucket from `athlete_position_abbreviation` — decide and document `ATH`/`NA` handling
- [x] Height, weight — join in directly from the Phase 1 master draft table (already resolved)
- [x] Missing-value handling: rely on tree models' native NaN handling; do not drop players for missing non-critical features
- [x] Assemble final training table: one row per drafted player (2019-2022) with all features above + placeholder for target (Phase 3)

### 2.3 Do not build (§4.2 — no data exists, confirm nothing downstream references these)
- Age at draft, class year (Fr/So/Jr/Sr)
- Wingspan, combine testing
- Conference, strength-of-schedule
- Any real advanced metric (BPM/VORP/WS) as an input feature

---

## Phase 3 — Target Construction: Projected Production Score (§2)

- [x] Implement Game Score per player-game from NBA box score columns: `PTS + 0.4·FGM − 0.7·FGA − 0.4·(FTA−FTM) + 0.7·ORB + 0.3·DRB + STL + 0.7·AST + 0.7·BLK − 0.4·PF − TOV`
- [x] Aggregate to PPS per player-season = mean Game Score across that season's games
- [x] For each drafted player (from the Phase 1 master draft table, which has real `Pk`/draft year), compute exact year-2 and year-3 NBA seasons from their real draft year (no inference needed — e.g. 2019 draft → year2 = season label 2021, year3 = season label 2022)
- [x] Target = mean(PPS year2, PPS year3)
- [x] Handle players with no NBA box score presence in year 2 and/or year 3 (never made the league, or missing a season) — exclude with a logged reason, don't impute a fake zero silently
- [x] Sanity-check target distribution and final row count once joined to Phase 2's feature table
- [x] Everywhere this value is stored/displayed, name the field `projected_production_score` / "Projected Production Score" — never `vorp`

---

## Phase 4 — Model Training (§5)

- [x] Implement cross-validation (k-fold or leave-one-out — required at this sample size, ~240 players)
- [x] Train primary model: XGBoost or LightGBM regressor on Projected Production Score
- [x] Train baseline: Random Forest regressor
- [x] Evaluate both via CV (MAE/RMSE, rank correlation vs actual PPS), record feature importances
- [x] Select final model, retrain on full 2019–2022 dataset
- [x] Serialize trained model + feature encoders/imputers (pickle/joblib)
- [x] Generate and persist predicted PPS for every player in the training set

---

## Phase 5 — Draft Simulation (§6.1, §6.2)

- [x] Load master draft table (Phase 1) as the real historical draft order: walk `Pk` 1→60 per year, 2019–2022, with `Tm` as team-on-the-clock
- [x] Implement sequential simulation: available pool at each pick = all eligible players minus only those actually already selected at earlier real picks — **never build a hypothetical alternate board based on prior model-driven picks** (write a test asserting this explicitly, per §6.1's integrity constraint)
- [x] Implement Pure BPA ranking: rank remaining pool by predicted PPS at each pick — **this is the required core deliverable**
- [x] Persist per-pick simulation output: pick number, team, player selected, full BPA-ranked available pool at time of pick

### 5.1 Optional stretch — positional-fit ranking (§6.2.2) — do not start until Phase 5 core is complete
- [ ] Derive each team's positional minutes distribution from their own prior-season NBA box scores (`data/nba/players`) — only feasible for the 2021 and 2022 draft classes (2019/2020 would need 2018-19/2019-20 rosters, not in the data)
- [ ] Apply discount/boost to remaining players' predicted PPS by position vs. that distribution
- [ ] Explicitly mark 2019/2020 picks as "not available" for this ranking in any output/UI — do not silently blank or fabricate values
- [ ] Skip entirely if time-constrained — this is not required for the POC to be complete

---

## Phase 6 — Grading (§6.3)

- [x] Compute rank differential per pick (BPA — required)
- [x] Compute value gap per pick: predicted PPS of #1-ranked available − predicted PPS of player actually selected (BPA — required)
- [x] If Phase 5.1 was built, compute both metrics for the fit-adjusted ranking too, with the 2019/2020 gap clearly flagged (n/a — Phase 5.1 was skipped, not built)
- [x] Persist per-pick grading table
- [x] Build team-level aggregate rollup → headline score/letter grade
- [x] Build trend view data: team's aggregate grade across 2019→2022

---

## Phase 7 — Pipeline Orchestration (§8.1)

- [x] Wire stages into a single runnable script/CLI: identity resolution → aggregation/feature engineering → target construction → model training → simulation → grading → write results
- [x] Make each stage independently re-runnable/cacheable
- [x] Finalize output schema, write final tables to local storage for dashboard consumption
- [x] Add a run log/summary: players resolved vs. excluded (with reasons), model CV scores, join-resolution warnings from Phase 1

---

## Phase 8 — Dashboard (§8.2)

- [x] Streamlit app skeleton reading only precomputed output files (no live inference)
- [x] Team selector, draft-year filter
- [x] Pick-by-pick drill-down (player selected, predicted PPS, #1-ranked alternative, rank differential, value gap)
- [x] Aggregate grade view (headline score/letter grade per team)
- [x] Trend view chart
- [x] If Phase 5.1 (fit-adjusted) was built, show it alongside BPA with the 2019/2020 coverage gap visibly marked, not hidden (n/a — Phase 5.1 was skipped, not built; dashboard explicitly notes Pure-BPA-only)
- [x] Every metric label reads "Projected Production Score" / "PPS" — never VORP
- [x] Load the `dataviz` skill conventions before building any charts

---

## Phase 9 — Narrative Generation (§7.4)

- [x] Build a function packaging a team's exact computed tables into a constrained Anthropic API prompt
- [x] Instruction prompt explicitly forbids inference/estimation beyond the provided numbers, and requires the model to say "Projected Production Score" (never VORP)
- [x] Add a grounding check for claims not traceable to the input tables
- [x] Wire narrative output into the dashboard's team report view
- [x] Cache generated narratives (avoid re-calling the API on every dashboard load)

---

## Phase 10 — Report Export (§8.3)

- [x] Standalone export function reusing the dashboard's data layer and grading logic (no duplicated logic)
- [x] Static HTML export of a team's full report
- [x] PDF export
- [x] Expose export as both a dashboard button and standalone CLI/script call

---

## Phase 11 — Validation & Wrap-up

- [x] End-to-end run on a clean environment, confirm no manual patching required
- [x] Spot-check Phase 1 join accuracy against a handful of well-known 2019-2022 picks (e.g. confirm Zion Williamson, Ja Morant resolve correctly end-to-end through all four data sources)
- [x] Spot-check grading output against well-known real draft outcomes as a sanity check on model + grading logic direction
- [x] Confirm §9 non-goals are genuinely out of scope in the shipped POC
- [x] Write a short README: how to run the pipeline, how to launch the dashboard, known limitations (left-censored trajectory feature, PPS is a proxy not real VORP, fit-adjusted ranking coverage gap if built, all §4.2 exclusions)
