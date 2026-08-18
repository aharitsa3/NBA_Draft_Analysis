"""Color constants for the dashboard's charts — the light-mode slice of the
`dataviz` skill's validated reference palette (see that skill's
`references/palette.md`). This dashboard doesn't implement a dark-mode
toggle (Streamlit's own theme system, not this palette, drives that), so
only the light values are needed.

Every chart here uses at most one series (line trend, magnitude bars), so
the categorical multi-hue palette isn't needed — only the single sequential
blue hue (magnitude) and the reserved status colors (grade-quality cue,
paired with the always-visible letter text, never color alone) are used.
"""

SERIES_BLUE = "#2a78d6"  # categorical slot 1 — the one series this dashboard ever draws alone

# Sequential blue ramp, light -> dark (steps 100-700), for magnitude encodings
# (league leaderboard bars, value-gap bars).
SEQUENTIAL_BLUE = [
    "#cde2fb",  # 100
    "#9ec5f4",  # 200
    "#6da7ec",  # 300
    "#3987e5",  # 400
    "#256abf",  # 500
    "#184f95",  # 600
    "#0d366b",  # 700
]

STATUS_GOOD = "#0ca30c"
STATUS_WARNING = "#fab219"
STATUS_SERIOUS = "#ec835a"
STATUS_CRITICAL = "#d03b3b"

# Collapses the 7-tier letter grade into the 4-step status palette for a
# supplementary color cue on grade badges — the letter text is always shown
# alongside it, so color is never the sole carrier of meaning.
GRADE_STATUS_COLOR = {
    "A": STATUS_GOOD,
    "B+": STATUS_GOOD,
    "B": STATUS_WARNING,
    "B-": STATUS_WARNING,
    "C+": STATUS_SERIOUS,
    "C": STATUS_SERIOUS,
    "F": STATUS_CRITICAL,
}

SURFACE = "#fcfcfb"
PRIMARY_INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
MUTED_INK = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
