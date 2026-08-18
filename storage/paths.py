"""Path constants for raw vs. processed data.

Raw source data lives in `data/` and is treated as read-only / tracked as-is.
Everything this pipeline computes is written under `processed_data/` instead,
so generated outputs never mix with or overwrite verified raw inputs.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DATA_DIR = PROJECT_ROOT / "processed_data"
