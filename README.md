# NBA Draft Analysis

A proof-of-concept pipeline that resolves 2019–2022 NBA draft picks across NCAA/NBA box
scores, builds a "Projected Production Score" (PPS) target from real year-2/year-3 NBA
production, trains a model to predict it from pre-draft college stats, simulates a
Pure Best-Player-Available draft against real historical picks, grades each team's actual
picks against that simulation, and presents it all in a Streamlit dashboard with optional
Claude-generated team narratives. See `nba_draft_analysis_design_doc.md` for the full
design spec and `tasks.md` for the phase-by-phase implementation checklist.

## Requirements

- Python 3.10+
- The `data/` directory (already present in this repo, tracked as-is — no scraping/fetch
  step exists anywhere in this pipeline)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the pipeline

```bash
python pipeline.py
```

Runs all seven stages in order (identity resolution → feature engineering → target
construction → model training → simulation → grading → finalize) and prints a run
summary. Each stage's outputs are cached under `processed_data/` (gitignored,
regenerated on demand) — a plain `python pipeline.py` skips any stage whose outputs
already exist. Force a full recompute with:

```bash
python pipeline.py --force
```

Run a single stage (assumes earlier stages already ran at least once):

```bash
python pipeline.py --stages model simulation grading finalize
```

Stage names, in pipeline order: `identity`, `features`, `target`, `model`, `simulation`,
`grading`, `finalize`. See the docstring at the top of `pipeline.py` for the caching
caveat around the `target` stage rewriting `features/training_table.parquet` in place.

Expected runtime: well under a minute end-to-end on a laptop (the dataset is ~240
players).

## Launching the dashboard

```bash
streamlit run dashboard/app.py
```

Reads only precomputed files under `processed_data/` — run the pipeline first. The
dashboard has three main sections for the team you select in the sidebar: a
league-wide grade leaderboard, that team's grade trend across 2019–2022, a
Claude-generated team report (optional, see below), and a pick-by-pick drill-down
with the full BPA-ranked pool at each pick.

## Exporting a team report (HTML / PDF)

From the CLI:

```bash
python -m reports.export --team BOS --format both
```

`--years 2019 2020` scopes it to specific draft years; `--output path` for a custom
file path (single-format only). The same export is also available as download buttons
in the dashboard sidebar.

## Team narratives (optional — two ways, one free)

A short Claude-written paragraph summarizing a team's draft performance can be
generated two ways:

**1. Live API call** (costs a small amount of usage — a few cents per team on Claude
Opus 5):

```bash
python -m reports.narrative generate --team BOS
```

Requires `ANTHROPIC_API_KEY` in a `.env` file at the project root (copy
`.env.example`). Also available as a "Generate via Anthropic API" button in the
dashboard.

**2. Free, manual paste — no API key needed:**

```bash
python -m reports.narrative prompt --team BOS
# → writes the exact prompt to processed_data/reports/prompts/BOS_prompt.txt
# → paste that file's contents into claude.ai (or any Claude chat), save the reply
python -m reports.narrative ingest --team BOS --file reply.txt
# → caches it exactly as a live API call would
```

Also available directly in the dashboard's "Generate for free via claude.ai" expander
(copy the shown prompt, paste the reply back into the box, save). Both paths write to
the same cache (`processed_data/reports/narratives.parquet`), keyed by a hash of the
team's exact input numbers — the dashboard/export can't tell which path produced a
given narrative, and a pipeline rerun that changes a team's numbers invalidates its
cached narrative automatically.

Every narrative passes through a heuristic **grounding check** that flags any number
in the text that doesn't trace back to the input data (a backstop against
fabricated numbers, not a semantic correctness check) — flagged narratives are shown
with a visible warning, never silently trusted.

## Running tests

```bash
python -m pytest tests/
```

Covers the §6.1 draft-simulation integrity constraint (Phase 5): the available player
pool at each simulated pick must be derived only from real historical selections at
earlier picks, never from the model's own suggestions.

## Known limitations

- **PPS is a proxy metric, not real VORP/BPM/Win Shares.** Those metrics don't exist
  in this dataset (only as career totals in `order.csv`, explicitly excluded — see
  §3.4/§4.2 of the design doc) and none were sourced. "Projected Production Score" is
  Hollinger Game Score averaged across a player's real year-2/year-3 NBA seasons.
  Every label in the codebase and UI says "PPS" / "Projected Production Score",
  never VORP.
- **The trained model has weak predictive signal from box-score-only features.**
  Out-of-fold rank correlation between predicted and actual PPS is ~0 for both models
  tried (Random Forest, selected, and XGBoost) — confirmed not an overfitting
  artifact (a heavily-regularized Ridge regression showed the same). Every individual
  §4.1 feature correlates weakly with the target (|r| < 0.17), while the real
  historical draft pick — deliberately excluded as a model input — correlates at
  −0.52. In other words, real scouts capture signal (athleticism, competition-level
  context, medical, makeup) that college box-score stats alone don't, and none of
  that is available in this dataset. This is a genuine, documented limitation of
  stat-only draft projection, not a bug — see `model/train.py`'s docstring. The
  **target construction itself is well-validated**, though: actual PPS tracks real
  draft-era reputations closely (e.g. Ja Morant, Paolo Banchero, Anthony Edwards,
  Cade Cunningham, and Evan Mobley all score 14.5–17.8; widely-regarded lesser picks
  like Killian Hayes and RJ Hampton score 4.8–8.6).
- **Years-of-college-data-available is left-censored.** It counts distinct NCAA
  seasons 2015–2022 a player appears in; a career that started before 2015 is
  undercounted. It's a lower bound on career length, not a verified class year (no
  birthdate/class-year field exists in the data to correct for this — see
  `features/trajectory.py`).
- **Positional-fit-adjusted ranking (design doc §6.2.2) was not built.** Only Pure
  BPA ranking exists — the dashboard and CLI outputs say so explicitly rather than
  presenting BPA as if it were the only possible ranking. This was an optional
  stretch goal per `tasks.md`, not a core deliverable, so its absence (rather than a
  partial 2021–2022-only implementation) is within scope.
- **§4.2 exclusions** (no data source exists for any of these, and none were added):
  age at draft, class year (Fr/So/Jr/Sr), wingspan, combine testing results,
  conference, strength-of-schedule/opponent adjustment, and any real advanced metric
  (BPM/VORP/Win Shares) as a model input feature.
- **Single-pick team-year grades can be noisy.** A team with exactly one pick in a
  given draft year that happened to match the model's #1-ranked available player
  gets a perfect grade from that one pick — `n_picks` is included in every grading
  output specifically so this can be judged, not hidden.
- **International/non-NCAA prospects are not specially handled** (an explicit
  non-goal, design doc §9) — they simply have no NCAA-side features, which the
  model handles via native NaN support, same as any other missing-feature case.
- **Everything is a one-time batch pipeline, not a live system** (also §9) — no
  scheduled refresh, no live model inference in the dashboard (it reads only
  precomputed `processed_data/` outputs), no outreach/distribution mechanism.

## Repository layout

| Path | Purpose |
|---|---|
| `identity/` | Phase 1 — name resolution, master draft table, NCAA/NBA join |
| `features/` | Phase 2 — NCAA season aggregation, feature engineering |
| `model/` | Phase 3–4 — target construction (PPS), model training/selection |
| `simulation/` | Phase 5 — sequential Pure BPA draft simulation |
| `grading/` | Phase 6 — per-pick and team-level grading |
| `dashboard/` | Phase 8 — Streamlit app |
| `reports/` | Phase 9–10 — Claude narratives, HTML/PDF export |
| `storage/` | Shared read/write helpers, path constants, config |
| `pipeline.py` | Phase 7 — single CLI orchestrating every stage |
| `tests/` | The §6.1 simulation-integrity test |
