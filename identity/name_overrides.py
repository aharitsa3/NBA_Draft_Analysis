"""Hand-verified name-variant overrides for players whose name differs between
data sources in a way that normalize_name() cannot fix (nicknames, legal-name vs.
common name, inconsistent suffixes). Each entry maps a normalized name as it
appears in one source to the normalized name it should be treated as equivalent
to for join purposes.

Built by: normalizing both sides of the picks<->order join per year, taking the
set difference, and manually researching every remaining unmatched name in
`data/nba/draft/picks` against the corresponding year's `data/nba/draft/order`
list (2019-2022). String-similarity search (difflib) was used to surface
candidates, and each candidate below was confirmed as the same real person
before being added — no override was added on the basis of similarity alone.

Names left unmatched after this table is applied are genuinely unresolvable
from these two files (most are players who actually went undrafted in real
life but still have a row in `picks.parquet` — e.g. Naz Reid, Jontay Porter,
Shamorie Ponds, Austin Reaves — or vice versa players present in `order.csv`
with no bio counterpart in `picks.parquet`, e.g. Cody Martin, Terance Mann).
These are logged, not silently dropped — see identity/draft_join.py.

Keys/values are normalize_name() output (lowercase, no periods/diacritics).
"""

# picks.parquet name -> order.csv name (same real person)
PICKS_TO_ORDER_NAME_OVERRIDES: dict[str, str] = {
    # 2019
    "marcos louzada silva": "didi louzada",  # Didi Louzada's legal/birth name
    # 2020
    "kenyon martin jr": "kj martin",  # goes by "KJ Martin"
    "xavier tillman": "xavier tillman sr",  # same person; BRef lists with "Sr." suffix
    # 2021
    "cameron thomas": "cam thomas",  # "Cameron" vs. common short form "Cam"
    "greg brown": "greg brown iii",  # BRef lists with "III" suffix
    "nah'shon hyland": "bones hyland",  # well-known nickname "Bones"
}
