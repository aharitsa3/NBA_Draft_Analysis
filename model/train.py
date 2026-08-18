"""Phase 4: cross-validate, train, select, and serialize the Projected
Production Score model (design doc §5).

Only the 185/238 players with a real Phase 3 target are used for CV/fitting —
you can't train or evaluate against a label that doesn't exist. But the final
model is used to predict every one of the 238 drafted players (Phase 5's draft
simulation needs a predicted PPS for every player in the pool at each pick,
including real-life non-targets like Zion Williamson's injury-shortened
sample or players who never made the NBA — the model still has their
pre-draft college features to predict from).

Cross-validation: 5-fold KFold (shuffled, fixed seed) — required at this
sample size per tasks.md; out-of-fold predictions are pooled across all folds
before scoring (more stable than averaging 5 tiny per-fold metrics at n=185).

**Known limitation, confirmed not a bug:** OOF rank correlation vs actual PPS
comes out near zero for both models (and for a heavily-regularized RidgeCV
sanity check tried during development). Every individual §4.1 feature also
has weak correlation with the target (|r| < 0.17), while the real historical
draft pick (deliberately excluded as a feature) correlates at -0.52 — i.e.
scouts capture real signal (athleticism, competition-level adjustment,
medical, makeup) that raw box-score stats alone don't, and §4.2 explicitly
excludes those inputs. This is a real, previously-documented difficulty of
stat-only draft projection, not a fixable modeling error at this feature set.

Run with: python -m model.train
"""

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold
from xgboost import XGBRegressor

from model.features import FEATURE_ENCODER, build_feature_matrix
from storage.io import read_parquet, write_parquet
from storage.paths import PROCESSED_DATA_DIR

RANDOM_STATE = 42
N_SPLITS = 5

MODEL_ARTIFACTS_DIR = PROCESSED_DATA_DIR / "model"


def _make_xgb() -> XGBRegressor:
    # Conservative hyperparameters — n=185 is tiny relative to typical GBT usage;
    # shallow trees + strong subsampling to limit overfitting.
    return XGBRegressor(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=RANDOM_STATE,
    )


def _make_rf() -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=500,
        max_depth=None,
        min_samples_leaf=3,
        random_state=RANDOM_STATE,
    )


def _cross_validate(X: pd.DataFrame, y: pd.Series, make_model) -> dict:
    kf = KFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    oof_pred = np.full(len(y), np.nan)

    for train_idx, val_idx in kf.split(X):
        model = make_model()
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        oof_pred[val_idx] = model.predict(X.iloc[val_idx])

    y_arr = y.to_numpy()
    mae = float(np.mean(np.abs(oof_pred - y_arr)))
    rmse = float(np.sqrt(np.mean((oof_pred - y_arr) ** 2)))
    rank_corr = float(spearmanr(oof_pred, y_arr).statistic)
    return {"mae": mae, "rmse": rmse, "rank_corr": rank_corr, "oof_pred": oof_pred}


def run() -> pd.DataFrame:
    MODEL_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    table = read_parquet("features/training_table.parquet")
    labeled = table[table["projected_production_score"].notna()].reset_index(drop=True)

    X_labeled = build_feature_matrix(labeled)
    y_labeled = labeled["projected_production_score"]

    print(f"Training set: {len(labeled)}/{len(table)} players with a computed target")
    print()

    results = {}
    for name, make_model in (("xgboost", _make_xgb), ("random_forest", _make_rf)):
        cv = _cross_validate(X_labeled, y_labeled, make_model)
        results[name] = cv
        print(f"--- {name} (5-fold CV, out-of-fold) ---")
        print(f"  MAE:  {cv['mae']:.3f}")
        print(f"  RMSE: {cv['rmse']:.3f}")
        print(f"  Rank correlation (Spearman) vs actual PPS: {cv['rank_corr']:.3f}")
        print()

    final_name = "xgboost" if results["xgboost"]["mae"] <= results["random_forest"]["mae"] else "random_forest"
    print(f"Selected final model: {final_name} (lower CV MAE)")
    print()

    make_final = _make_xgb if final_name == "xgboost" else _make_rf
    final_model = make_final()
    final_model.fit(X_labeled, y_labeled)

    print(f"--- {final_name} feature importances (fit on full labeled set) ---")
    importances = pd.Series(final_model.feature_importances_, index=X_labeled.columns).sort_values(ascending=False)
    print(importances)
    print()

    joblib.dump(final_model, MODEL_ARTIFACTS_DIR / "final_model.joblib")
    joblib.dump(FEATURE_ENCODER, MODEL_ARTIFACTS_DIR / "feature_encoder.joblib")
    joblib.dump(
        {
            "final_model_name": final_name,
            "cv_results": {k: {m: v[m] for m in ("mae", "rmse", "rank_corr")} for k, v in results.items()},
            "feature_importances": importances.to_dict(),
        },
        MODEL_ARTIFACTS_DIR / "training_summary.joblib",
    )

    X_all = build_feature_matrix(table)
    predicted_pps = final_model.predict(X_all)

    predictions = table[["draft_year", "pick", "player_name", "projected_production_score"]].copy()
    predictions = predictions.rename(columns={"projected_production_score": "actual_pps"})
    predictions["predicted_pps"] = predicted_pps
    predictions["used_in_training"] = table["projected_production_score"].notna()
    write_parquet(predictions, "model/predictions.parquet")

    print(f"Persisted predictions for all {len(predictions)} players -> processed_data/model/predictions.parquet")
    print(f"Persisted model artifacts -> {MODEL_ARTIFACTS_DIR}")

    return predictions


if __name__ == "__main__":
    run()
