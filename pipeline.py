#!/usr/bin/env python3
"""Phase 7: single pipeline entrypoint (design doc §8.1).

Wires every stage into one runnable CLI: identity resolution -> feature
engineering -> target construction -> model training -> simulation ->
grading -> write final results. Each stage's real logic lives in its own
module (identity/, features/, model/, simulation/, grading/) — this script
only orchestrates: it decides run order, does existence-based caching per
stage, and assembles the final dashboard-ready output + run summary.

Caching is existence-based, not dependency-hash-based: a stage is skipped if
all of its declared output files already exist, unless --force is passed.
This is coarse on purpose (no DAG/hash-tracking infra) — note that the
`target` stage rewrites `features/training_table.parquet` in place (folding
the real Projected Production Score into Phase 2's output), so re-running
`features` alone after `target` has already run will NOT restore Phase 2's
placeholder-target version; pass --force if you specifically need to rebuild
`features` from scratch. Running an individual stage standalone (via
--stages) also assumes every earlier stage has been run at least once —
storage/io.py raises a clear FileNotFoundError naming the missing input if not.

Usage:
  python pipeline.py                             # run every stage (skip ones already cached)
  python pipeline.py --force                      # ignore cache, recompute every stage
  python pipeline.py --stages model simulation     # run only these stages, in pipeline order
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import joblib
import pandas as pd

from storage.io import read_parquet, write_parquet
from storage.paths import PROCESSED_DATA_DIR


@dataclass
class Stage:
    name: str
    description: str
    outputs: list[str]  # paths relative to PROCESSED_DATA_DIR
    run: Callable[[], object]

    def outputs_exist(self) -> bool:
        return all((PROCESSED_DATA_DIR / p).exists() for p in self.outputs)


def _stage_identity():
    from identity.validate import run

    run()


def _stage_features():
    from features.build_training_table import build_training_table

    build_training_table()


def _stage_target():
    from model.build_target import run

    run()


def _stage_model():
    from model.train import run

    run()


def _stage_simulation():
    from simulation.draft_sim import run

    run()


def _stage_grading():
    from grading.grade import run

    run()


def _stage_finalize():
    finalize_results()


STAGES = [
    Stage(
        "identity",
        "Phase 1: identity resolution & master draft table",
        [
            "identity/master_draft_table.parquet",
            "identity/draft_join_report.parquet",
            "identity/box_score_unresolved.parquet",
        ],
        _stage_identity,
    ),
    Stage(
        "features",
        "Phase 2: NCAA season aggregation & feature engineering",
        ["features/training_table.parquet", "features/no_ncaa_season_players.parquet"],
        _stage_features,
    ),
    Stage(
        "target",
        "Phase 3: Projected Production Score target construction",
        ["model/target_table.parquet"],
        _stage_target,
    ),
    Stage(
        "model",
        "Phase 4: model training & selection",
        ["model/final_model.joblib", "model/feature_encoder.joblib", "model/predictions.parquet"],
        _stage_model,
    ),
    Stage(
        "simulation",
        "Phase 5: sequential Pure BPA draft simulation",
        ["simulation/picks.parquet", "simulation/available_pool.parquet"],
        _stage_simulation,
    ),
    Stage(
        "grading",
        "Phase 6: pick grading & team rollups",
        ["grading/pick_grades.parquet", "grading/team_rollup.parquet"],
        _stage_grading,
    ),
    Stage(
        "finalize",
        "Phase 7: assemble final dashboard-ready table + run summary",
        ["pipeline/final_report.parquet", "pipeline/run_summary.txt"],
        _stage_finalize,
    ),
]


def _load_training_summary() -> dict | None:
    path = PROCESSED_DATA_DIR / "model" / "training_summary.joblib"
    return joblib.load(path) if path.exists() else None


def assemble_final_report() -> pd.DataFrame:
    """One row per real pick, 2019-2022: every feature, the real vs. predicted
    target, and the BPA/grading columns — the single table Phase 8's dashboard
    reads from, so it never has to join Phase 2/3/5/6 outputs itself.
    """
    training_table = read_parquet("features/training_table.parquet")
    pick_grades = read_parquet("grading/pick_grades.parquet")
    team_rollup = read_parquet("grading/team_rollup.parquet")

    sim_cols = [
        "draft_year",
        "pick",
        "predicted_pps_selected",
        "bpa_top_player",
        "bpa_top_predicted_pps",
        "bpa_rank_of_selected",
        "pool_size",
        "rank_differential",
        "value_gap",
    ]
    report = training_table.merge(pick_grades[sim_cols], on=["draft_year", "pick"], how="left")

    team_cols = ["team_abbreviation_espn", "draft_year", "n_picks", "headline_score", "grade_letter"]
    report = report.merge(
        team_rollup[team_cols].rename(columns={"n_picks": "team_draft_year_n_picks"}),
        on=["team_abbreviation_espn", "draft_year"],
        how="left",
    )

    return report.rename(columns={"projected_production_score": "actual_pps"})


def build_run_summary(report: pd.DataFrame) -> str:
    master = read_parquet("identity/master_draft_table.parquet")
    join_report = read_parquet("identity/draft_join_report.parquet")
    box_unresolved = read_parquet("identity/box_score_unresolved.parquet")
    no_ncaa_season = read_parquet("features/no_ncaa_season_players.parquet")
    training_summary = _load_training_summary()

    n = len(master)
    n_bio = int(master["bio_matched"].sum())
    n_ncaa = int(master["athlete_id_ncaa"].notna().sum())
    n_nba = int(master["athlete_id_nba"].notna().sum())
    n_target = int(report["actual_pps"].notna().sum())
    n_team_years = report[["team_abbreviation_espn", "draft_year"]].drop_duplicates().shape[0]

    lines = [
        "NBA Draft Analysis — pipeline run summary",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "== Phase 1: Identity Resolution ==",
        f"  {n} real picks, 2019-2022",
        f"  bio matched: {n_bio}/{n} ({n_bio / n:.1%})",
        f"  NCAA resolved: {n_ncaa}/{n} ({n_ncaa / n:.1%})",
        f"  NBA resolved: {n_nba}/{n} ({n_nba / n:.1%})",
        f"  join-resolution warnings logged: {len(join_report)} (picks<->order) "
        f"+ {len(box_unresolved)} (box score) — see identity/*.parquet for details, never silently dropped",
        "",
        "== Phase 2: Feature Engineering ==",
        f"  players with no NCAA season found: {len(no_ncaa_season)} "
        f"-> {no_ncaa_season['player_name'].tolist()}",
        "",
        "== Phase 3: Target Construction ==",
        f"  projected_production_score computed: {n_target}/{len(report)} ({n_target / len(report):.1%})",
        "",
        "== Phase 4: Model Training ==",
    ]

    if training_summary:
        lines.append(f"  selected model: {training_summary['final_model_name']}")
        for model_name, cv in training_summary["cv_results"].items():
            lines.append(
                f"  {model_name} CV (out-of-fold): MAE={cv['mae']:.3f} "
                f"RMSE={cv['rmse']:.3f} rank_corr={cv['rank_corr']:.3f}"
            )
    else:
        lines.append("  (no training_summary.joblib found — run the `model` stage)")

    lines += [
        "",
        "== Phase 5/6: Simulation & Grading ==",
        f"  picks simulated: {len(report)}",
        f"  mean rank differential: {report['rank_differential'].mean():.2f}",
        f"  mean value gap (PPS points): {report['value_gap'].mean():.2f}",
        f"  team-year rollups graded: {n_team_years}",
        "",
        "== Final output ==",
        f"  processed_data/pipeline/final_report.parquet — {len(report)} rows, {len(report.columns)} columns",
    ]

    return "\n".join(lines)


def finalize_results() -> pd.DataFrame:
    report = assemble_final_report()
    write_parquet(report, "pipeline/final_report.parquet")

    summary_text = build_run_summary(report)
    (PROCESSED_DATA_DIR / "pipeline").mkdir(parents=True, exist_ok=True)
    (PROCESSED_DATA_DIR / "pipeline" / "run_summary.txt").write_text(summary_text)
    print(summary_text)

    return report


def run_stage(stage: Stage, force: bool) -> None:
    if not force and stage.outputs_exist():
        print(f"[skip] {stage.name}: outputs already exist (use --force to recompute) — {stage.description}")
        return
    print(f"[run ] {stage.name}: {stage.description}")
    stage.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the NBA draft analysis pipeline (design doc §8.1).")
    parser.add_argument(
        "--stages",
        nargs="+",
        choices=[s.name for s in STAGES],
        help="Run only these stages, in pipeline order (default: all)",
    )
    parser.add_argument(
        "--force", action="store_true", help="Recompute every selected stage even if its outputs already exist"
    )
    args = parser.parse_args()

    selected_names = set(args.stages) if args.stages else {s.name for s in STAGES}
    selected = [s for s in STAGES if s.name in selected_names]

    print(f"Pipeline run: {len(selected)} stage(s) -> {[s.name for s in selected]}")
    print()
    for stage in selected:
        run_stage(stage, args.force)
        print()

    print("Pipeline complete.")


if __name__ == "__main__":
    main()
