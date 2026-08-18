"""Static Basketball-Reference -> ESPN team abbreviation mapping.

`data/nba/draft/order/order_*.csv` (`Tm` column) uses Basketball-Reference-style
abbreviations. `data/nba/players/player_box_*.parquet` (`team_abbreviation`
column) uses ESPN-style abbreviations. The two only disagree for a handful of
teams (Brooklyn, Charlotte, Golden State, New Orleans, New York, Phoenix, San
Antonio, Utah, Washington); everywhere else the codes are identical.

Verified: both sides enumerate exactly the 30 real NBA franchises (confirmed
against `order_2019..2022.csv` `Tm` values and `player_box_2021.parquet`
`team_abbreviation` values, excluding the two non-franchise All-Star-draft
codes 'DUR'/'LEB' that also appear in the box score data).
"""

BREF_TO_ESPN_TEAM_ABBR: dict[str, str] = {
    "ATL": "ATL",
    "BOS": "BOS",
    "BRK": "BKN",  # Brooklyn Nets
    "CHI": "CHI",
    "CHO": "CHA",  # Charlotte Hornets
    "CLE": "CLE",
    "DAL": "DAL",
    "DEN": "DEN",
    "DET": "DET",
    "GSW": "GS",  # Golden State Warriors
    "HOU": "HOU",
    "IND": "IND",
    "LAC": "LAC",
    "LAL": "LAL",
    "MEM": "MEM",
    "MIA": "MIA",
    "MIL": "MIL",
    "MIN": "MIN",
    "NOP": "NO",  # New Orleans Pelicans
    "NYK": "NY",  # New York Knicks
    "OKC": "OKC",
    "ORL": "ORL",
    "PHI": "PHI",
    "PHO": "PHX",  # Phoenix Suns
    "POR": "POR",
    "SAC": "SAC",
    "SAS": "SA",  # San Antonio Spurs
    "TOR": "TOR",
    "UTA": "UTAH",  # Utah Jazz
    "WAS": "WSH",  # Washington Wizards
}

assert len(BREF_TO_ESPN_TEAM_ABBR) == 30
