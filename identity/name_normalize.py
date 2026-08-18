"""Player-name normalization for use as a join key everywhere a name is matched
across data sources (draft picks <-> draft order <-> NCAA box scores <-> NBA box scores).

Handles: periods (P.J. -> PJ), diacritics/transliteration (Luka Šamanić -> Luka Samanic),
whitespace collapsing, and case-folding. Does NOT handle nickname/legal-name variants
(e.g. "Didi Louzada" vs "Marcos Louzada Silva") or suffix differences (Jr/Sr/III/IV
inconsistently applied across sources) — those are handled by the explicit override
table in name_overrides.py, since they require per-player human judgment, not a
general string transform.
"""

import re
import unicodedata


def normalize_name(name) -> str | None:
    if name is None or (isinstance(name, float) and str(name) == "nan"):
        return None
    s = str(name).strip()
    if not s or s.lower() == "nan":
        return None
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.replace(".", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower()
