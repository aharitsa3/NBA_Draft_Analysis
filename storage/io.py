"""Read/write helpers for processed pipeline outputs.

All writes are scoped under PROCESSED_DATA_DIR — never under RAW_DATA_DIR —
so pipeline stages can freely re-run and overwrite their own outputs without
any risk of touching the raw `data/` inputs.
"""

from pathlib import Path

import pandas as pd

from storage.paths import PROCESSED_DATA_DIR


def _resolve(relative_path: str | Path) -> Path:
    path = PROCESSED_DATA_DIR / relative_path
    if PROCESSED_DATA_DIR not in path.resolve().parents and path.resolve() != PROCESSED_DATA_DIR:
        raise ValueError(f"Refusing to write outside processed data dir: {path}")
    return path


def write_parquet(df: pd.DataFrame, relative_path: str | Path) -> Path:
    """Write a DataFrame to `processed_data/<relative_path>`, creating parent dirs as needed."""
    path = _resolve(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def read_parquet(relative_path: str | Path) -> pd.DataFrame:
    """Read a DataFrame from `processed_data/<relative_path>`."""
    path = _resolve(relative_path)
    if not path.exists():
        raise FileNotFoundError(
            f"No processed output at {path}. Has the stage that produces it been run?"
        )
    return pd.read_parquet(path)


def exists(relative_path: str | Path) -> bool:
    return _resolve(relative_path).exists()
