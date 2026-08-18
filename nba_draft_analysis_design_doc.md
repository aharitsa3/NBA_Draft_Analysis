# NBA Draft Analysis — Design Document (POC)

**Purpose of this document:** Hand-off spec for an implementing agent/engineer. This is v2 of the design doc, rewritten after directly inspecting the actual dataset provided in `data/` — every data claim below has been verified against the real files, not assumed. This is a POC (proof of concept), not a production system.

**Change from v1:** the original design assumed sportsdataverse pulls plus supplemental sourcing from Basketball-Reference/NBA Combine. In practice, the project owner supplied a fixed local dataset and will not be sourcing anything further. This version scopes the project entirely to what that dataset actually contains.

---

## 1. Project Summary

Build a system that:
1. Trains an ML model on college basketball statistics to predict a player's future NBA production.
2. Simulates the actual historical draft order (2019–2022, all rounds), and at each pick, determines the "best available" player per the model.
3. Compares each team's actual selection against the model's recommendation to grade draft decisions.
4. Surfaces this via an interactive Streamlit dashboard and an exportable static report per team.

This is a portfolio/demonstration project — not intended for literal distribution to NBA front offices.

---

## 2. Prediction Target

**No advanced metric (VORP, BPM, Win Shares) exists anywhere in the provided dataset** — the only place these appear is `data/nba/draft/order/order_*.csv`, and there only as whole-career cumulative totals as of whenever that table was last updated, not broken out by season. Per the project owner's decision, those columns are excluded entirely (see §3.4) — only `Pk` (pick number) and `Tm` (drafting team) are used from that file.

- **Metric:** **Projected Production Score (PPS)** — a per-game "Game Score" composite (Hollinger's formula), computed entirely from raw box score columns that are present in `data/nba/players/`:

  ```
  Game Score = PTS + 0.4·FGM − 0.7·FGA − 0.4·(FTA−FTM)
             + 0.7·ORB + 0.3·DRB + STL + 0.7·AST + 0.7·BLK − 0.4·PF − TOV
  ```

  PPS for a player-season = mean Game Score across that season's games. The model target = average of PPS across the player's **years 2 and 3 post-draft**.

- **Window:** years 2 and 3 post-draft, excluding rookie year — same rationale as the original design (rookie-year minutes/role are too noisy to reflect true talent). Because we now have each player's **real, verified draft year** (from `order.csv`, see §3.4), year 2 and year 3 are computed exactly, not inferred.
- **Explicit labeling requirement:** every dashboard view, report, and generated narrative must call this metric **"Projected Production Score"** or **"PPS"** — never "VORP." It is a proxy built for this POC, not the real Basketball-Reference statistic, and must not be presented as such.

---

## 3. Data Sources (verified inventory)

All data lives in `data/`, already provided — no fetching, scraping, or additional sourcing occurs anywhere in this project.

### 3.1 NCAA box scores — `data/ncaa/players/`, `data/ncaa/teams/`

Game-level (one row per player/team per game), seasons 2015–2022, one parquet file per season. **Season label = the calendar year the season ends** (verified directly: `player_box_2019.parquet` contains games from Nov 2018 through the April 2019 championship game — i.e. season label `2019` = the 2018-19 season).

- Player file: FGM/FGA, 3PM/3PA, FTM/FTA, ORB/DRB, AST/STL/BLK/TOV, fouls, points, minutes, starter flag, `athlete_position_abbreviation` (PG/SG/SF/PF/C/G/F, plus `ATH`/`NA` for unclassified), `athlete_id`, `team_id`, `opponent_team_id`. `season_type`: 2 = regular season, 3 = postseason.
- Team file: team-level FGM/FGA/3PM/3PA/FTM/FTA/ORB/DRB/TOV/fouls per team-game. `team_id` joins 1:1 to the player file's `team_id` (verified: 652/652 overlap in the 2019 season).
- **Not present:** possessions/pace (must derive), conference (no field anywhere in either file).

### 3.2 NBA box scores — `data/nba/players/`

Game-level, seasons 2021–2025, same season-labeling convention (verified: `player_box_2021.parquet` spans Dec 2020 – July 2021, the COVID-shifted 2020-21 season). Same box score columns as NCAA, plus `plus_minus`. `season_type`: 2 = regular, 3 = postseason, 5 = play-in.

- **Not present:** any advanced metric (VORP/BPM/WS), and no `data/nba/teams/` folder exists — no NBA team box scores or schedule (no pace/possessions context on the NBA side).

### 3.3 Draft player bio — `data/nba/draft/picks/draft_*.parquet` (2019–2022, 60 rows/year = both rounds)

Contains `athlete_display_name`, `athlete_height`, `athlete_weight` (**fully populated across all 4 years — physical measurables gap from v1 is resolved**), position, and a `college_name` field that is **entirely null in every year** (unusable).

**Verified data quality issue — do not trust this file's own draft-position fields:** `pick`, `overall_pick`, `round`, and `team_id` in this file do not match real recorded draft history. Cross-checked by name against `order.csv` for 2019: 40 of 44 name-matched players have a different pick number between the two files (e.g. Sekou Doumbouya is listed as pick 8 here, but pick 15 — the real, well-documented value — in `order.csv`). **Decision: ignore `pick`/`overall_pick`/`round`/`team_id` in this file entirely.** Use it only for player bio attributes (name, height, weight, position).

Also verified: `athlete_id` in this file is a **different ID namespace** than the `athlete_id` used in the NCAA/NBA box score files (e.g. Zion Williamson is `102976` here vs. `4395628` in the NCAA box file). It cannot be used as a join key to box score data — joins must go through normalized player name instead.

### 3.4 Draft order — `data/nba/draft/order/order_*.csv` (2019–2022, 60 rows/year)

Basketball-Reference-style draft table. Columns: `Rk`, `Pk`, `Tm`, `Player`, `College`, `Yrs`, career-total counting stats, shooting splits, per-game stats, and advanced stats (`WS`, `WS/48`, `BPM`, `VORP` — all career-to-date cumulative totals).

**Decision (per project owner): use only `Pk` and `Tm` from this file** as the authoritative real draft order and drafting team — `Pk`'s values were spot-checked against well-documented draft history and are correct where `picks.parquet` was wrong. All other columns (career totals, per-game stats, advanced stats) are explicitly excluded from this project; they are not year-2/3-specific and are not used anywhere.

`Tm` uses Basketball-Reference team abbreviations (`PHO`, `BRK`, `CHO`, ...), which differ from the ESPN-style abbreviations used in the NBA box score files (`PHX`, `BKN`, `CHA`, ...) — a static ~30-row mapping table is required to join a drafting team to that team's box score rows.

### 3.5 Join strategy across all sources

- **Draft bio ↔ draft order:** join by normalized player name within a draft year. Verified ~73% exact-string match rate (44/60 in the 2019 sample); remaining mismatches are name-formatting differences (`PJ Washington` vs `P.J. Washington`, `Luka Samanic` vs `Luka Šamanić`, nickname vs. legal name). Build a normalization pass (strip periods, transliterate diacritics) then hand-resolve the remainder — small enough (~15-20 players/year) for manual review.
- **Draft player ↔ NCAA/NBA box score player:** join by normalized player name (not `athlete_id` — see §3.3). Same normalization approach; watch for common-name collisions in box score files (multiple distinct players can share a display name — spot-checked in NCAA 2019 data).
- **Drafting team ↔ box score team:** static BRef-abbreviation → ESPN-abbreviation/`team_id` mapping table (~30 rows, one-time, hand-built).

---

## 4. Feature Set

### 4.1 Computable now from available data

| Feature | Derivation |
|---|---|
| eFG%, FT Rate | Direct from NCAA player box (FGM, 3PM, FGA, FTA, FTM) |
| TOV% (individual) | `TOV / (FGA + 0.44·FTA + TOV)`, direct from player box |
| ORB%, Usage Rate | Require team-game context — join player box to `data/ncaa/teams` on `team_id`+`game_id` (and opponent row via `opponent_team_id`) |
| PPG, RPG, APG, SPG, BPG, minutes | Aggregate NCAA player box to season level |
| Team pace/possessions | `Poss ≈ FGA − ORB + TOV + 0.44·FTA`, from `data/ncaa/teams`, per team-season |
| Years-of-college-data-available (trajectory proxy) | Count of distinct NCAA seasons a given player appears in, 2015–2022. **Caveat:** left-censored for players whose career started before 2015 — document as a known limitation, do not treat as true class year |
| Position bucket | `athlete_position_abbreviation` from NCAA box; decide handling for `ATH`/`NA` |
| Height, weight | From `data/nba/draft/picks` (fully populated, resolved gap from v1) |

### 4.2 Explicitly out of scope (no data, none will be sourced)

- Age at draft, class year (Fr/So/Jr/Sr) — no birthdate or class-year field anywhere in the dataset
- Wingspan, combine testing results — not in any provided file
- Conference — no conference field in NCAA player or team box files
- Strength-of-schedule/opponent adjustment — would require conference/ranking context not present
- Any true advanced metric (real BPM/VORP/WS) as an input feature — only available as career totals in `order.csv`, which are excluded per §3.4

**Design principle (unchanged from v1):** the feature pipeline degrades gracefully — missing non-critical features are handled via tree models' native NaN handling, not by dropping players.

---

## 5. Model

- **Primary:** XGBoost or LightGBM (gradient-boosted trees)
- **Baseline/sanity check:** Random Forest
- **Rationale:** small tabular dataset (~240 players across 4 draft classes, now roughly 10-15 features given §4.2 exclusions). Boosted trees handle nonlinearity/interactions well and give feature importances for report explainability; a neural net is ruled out given sample size.
- **Validation:** k-fold or leave-one-out cross-validation — a single train/test split is not reliable at this sample size.
- **Output:** predicted Projected Production Score (continuous value) per player.

---

## 6. Draft Simulation & Grading Logic

### 6.1 Simulation mechanics — sequential, real draft order

- Walk through the **actual historical draft order** (`order.csv` `Pk`, 2019–2022, all rounds), pick by pick.
- At each pick, the "available pool" = all eligible players **minus only the players who were actually already selected** at earlier picks in the real draft.
- **Critical constraint (unchanged from v1, still the core integrity requirement):** the simulation must NEVER build a hypothetical alternate draft board based on what the model thinks *should* have happened at prior picks. "Best available" at pick #14 is always computed against the real world after real picks #1-13.

### 6.2 Ranking types

1. **Pure Best Player Available (BPA):** rank remaining pool purely by predicted PPS. **This is the core deliverable, fully supported by the data for all 4 draft classes.**
2. **Positional-fit-adjusted ranking — optional stretch goal, partial coverage only.** The original design called for roster depth-chart/minutes-by-position data, which does not exist in this dataset and will not be sourced. A rough proxy is possible: derive each drafting team's positional minutes distribution from their own prior-season NBA box scores (`data/nba/players`). This only works for the **2021 and 2022** draft classes, since the "prior season" for the 2019 and 2020 classes (2018-19 and 2019-20) predates the NBA box score data we have (which starts at season label 2021). **Do not build this as a required deliverable** — implement BPA fully first; treat fit-adjustment as an add-on that, if built, must clearly label itself as unavailable for the 2019/2020 classes rather than silently omitting or faking values.
3. Timeline-fit (win%, roster age) remains explicitly deferred, same as v1 — no NBA team standings/win% data exists in this dataset either, so even the "schema placeholder, unused" approach from v1 has no source to populate it from. Omit the placeholder fields rather than inventing them.

### 6.3 Grading metrics, per pick

- **Rank differential:** where the actual selection ranked among available players by predicted PPS.
- **Value gap:** predicted PPS of #1-ranked available player − predicted PPS of player actually selected.
- Both computed for BPA (required). If the fit-adjusted ranking (§6.2.2) is built, compute both metrics for it too, shown side by side, with the 2019/2020 coverage gap clearly marked in the UI.

---

## 7. Report Contents (per team)

Each team-specific report should include:

1. **Pick-by-pick table** — for every pick that team made across 2019-2022: player selected, model's predicted PPS for them, #1-ranked available alternative, rank differential, value gap.
2. **Aggregate grade** — team-level rollup (summed/averaged value gap across all picks) producing a headline score/letter grade.
3. **Trend view** — how the team's drafting performance evolved across the 4 draft classes.
4. **Auto-generated narrative** — natural-language summary via the Anthropic API.
   - **Constraint (unchanged from v1):** the LLM is given only the exact computed numbers/tables for that team and instructed to narrate only what's in the provided data — no independent inference. It must also consistently refer to the target metric as "Projected Production Score," never VORP.

---

## 8. Application Architecture

### 8.1 Pipeline (batch, one-time for POC)

```
load (read data/ncaa, data/nba/players, data/nba/draft/picks, data/nba/draft/order — all local, no fetching)
  → identity resolution (name-normalize + join picks ↔ order ↔ box scores ↔ team abbreviations, §3.5)
  → feature engineering (§4.1 only; NCAA season aggregation, Four Factors, pace, trajectory)
  → target construction (Projected Production Score from NBA box scores, years 2 & 3 by real draft year)
  → model training (XGBoost/LightGBM + Random Forest baseline, cross-validated)
  → draft simulation (sequential, real order via order.csv — §6.1)
  → grading (rank differential + value gap, BPA required / fit-adjusted optional — §6.3)
  → write results to local storage
```

- **Storage:** local Parquet or SQLite files, separate from the raw `data/` inputs.
- Model artifacts (trained model, feature encoders) serialized (pickle/joblib) for dashboard reuse without retraining.
- No forward-compatibility work needed for adding future draft classes beyond what's naturally supported by re-running with a new `order.csv`/`picks.parquet`/box score files, if the owner ever supplies them — but no such addition is currently planned.

### 8.2 Dashboard

- **Tool:** Streamlit.
- **Core interactions:** team selector, draft-year filter, per-pick drill-down.
- **Data source:** reads precomputed results only — no live model inference or live scraping triggered by dashboard interaction.
- Every place the metric is displayed, label it "Projected Production Score" / "PPS," not VORP.

### 8.3 Report export function

- Separate function (callable from the dashboard or standalone) that snapshots a team's report into a static shareable document (HTML and/or PDF).
- Shares the same underlying data layer as the dashboard — no duplicated grading logic.

---

## 9. Explicit Non-Goals for POC

- Real VORP/BPM/Win Shares as the model target or an input feature — approximated via Projected Production Score instead (§2), since the real metric does not exist in this dataset and will not be sourced.
- Age at draft, class year, wingspan, combine testing, conference, strength-of-schedule — no data source exists for any of these and none will be added (§4.2).
- Full-coverage positional-fit adjustment — at most a partial (2021-2022 only) stretch goal (§6.2), not a core deliverable.
- Timeline/win-context fit adjustment, including as an unused schema placeholder — no source data exists for it at all.
- International/non-NCAA prospects.
- Live/refreshing pipeline or live model inference.
- Literal outreach/distribution to NBA teams.
- Archetype-based skillset-redundancy fit (beyond simple positional need).

---

## 10. Open Items for Implementing Agent

- Build and hand-verify the name-normalization + matching logic across `picks.parquet` ↔ `order.csv` ↔ NCAA/NBA box scores (§3.5) — this is the single highest-risk step in the pipeline; a silent bad match corrupts a player's entire feature/target row.
- Build and verify the BRef ↔ ESPN team abbreviation mapping table (§3.4) before it's used anywhere downstream.
- Decide and document the `ATH`/`NA` position-bucket handling (§4.1) before it affects any position-dependent feature.
- If the positional-fit stretch goal (§6.2.2) is attempted, make the 2019/2020 coverage gap visible in the UI rather than silently blank.
