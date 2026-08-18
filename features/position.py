"""Position bucket from `athlete_position_abbreviation` (design doc §4.1).

Maps the raw NCAA position label to a 3-way bucket: G / F / C. Hybrid labels
("G-F", "F-C") are bucketed by their first listed component. `ATH` (pure
athlete, no position recorded) and `NA`/missing are bucketed as "UNK" — kept
as an explicit category rather than imputed, so the model sees it as a
distinct (uninformative) case rather than a false NaN.
"""

import pandas as pd

POSITION_BUCKET_MAP: dict[str, str] = {
    "PG": "G", "SG": "G", "G": "G", "G-F": "G",
    "SF": "F", "PF": "F", "F": "F", "F-C": "F",
    "C": "C",
}


def position_bucket(raw_position) -> str:
    if raw_position is None or (isinstance(raw_position, float) and pd.isna(raw_position)):
        return "UNK"
    return POSITION_BUCKET_MAP.get(str(raw_position), "UNK")
