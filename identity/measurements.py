"""Parse `picks.parquet`'s string-formatted height/weight into numeric values.

`athlete_height` is formatted like `6' 6"`, `athlete_weight` like `272 lbs`
(verified consistent across all four draft years). A handful of weight values
are the literal sentinel string `"0"` (Yam Madar 2020; Jabari Smith Jr. and
Nikola Jovic 2022) — not a real weight, treated as missing.
"""

import re

_HEIGHT_RE = re.compile(r"^(\d+)'\s*(\d+)\"$")


def parse_height_inches(raw) -> float | None:
    if raw is None:
        return None
    match = _HEIGHT_RE.match(str(raw).strip())
    if not match:
        return None
    feet, inches = match.groups()
    return int(feet) * 12 + int(inches)


def parse_weight_lbs(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "0":
        return None
    match = re.match(r"^(\d+)\s*lbs$", s)
    return int(match.group(1)) if match else None
