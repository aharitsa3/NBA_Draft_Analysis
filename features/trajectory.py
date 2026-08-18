"""Years-of-college-data-available trajectory proxy (tasks.md §2.2).

Counts distinct NCAA seasons (2015-2022) a player appears in
`data/ncaa/players`, regardless of played-vs-DNP status — this measures data
availability (was the player on file that season), not games played.

**Left-censoring caveat:** the earliest season in the data is 2015. A player
whose college career started before 2015 will be undercounted — this is a
lower bound on true career length, not a verified class year (there is no
birthdate or class-year field anywhere in the dataset to correct for this,
per §4.2 of the design doc).
"""

import pandas as pd

from storage.paths import RAW_DATA_DIR

NCAA_SEASONS = list(range(2015, 2023))


def build_years_of_data_available() -> pd.Series:
    """Returns a Series indexed by athlete_id: count of distinct seasons 2015-2022 they appear in."""
    frames = []
    for season in NCAA_SEASONS:
        path = RAW_DATA_DIR / "ncaa" / "players" / f"player_box_{season}.parquet"
        frames.append(pd.read_parquet(path, columns=["athlete_id", "season"]).drop_duplicates())
    allp = pd.concat(frames, ignore_index=True)
    return allp.groupby("athlete_id")["season"].nunique().rename("years_of_college_data_available")
