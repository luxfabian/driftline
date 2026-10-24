"""Design tokens: Sanzo Wada, A Dictionary of Color Combinations, No. 309.

Golden Yellow, Apricot Orange, Vandar Poel's Blue and Violet Blue, on warm
paper. The four colors are used as printed for the interface (navigation,
text, buttons, accents). Chart series use the same hues re-stepped in OKLCH
into the readable band, validated with the dataviz palette validator
(adjacent CVD ΔE >= 14.9; first three slots also pass all-pairs).
``assets/theme.css`` defines the same values as CSS variables.
"""

from __future__ import annotations

# --- Wada No. 309, as printed ----------------------------------------------------
GOLDEN_YELLOW = "#f3a257"
APRICOT_ORANGE = "#f68c50"
VANDAR_POELS_BLUE = "#064f6e"
VIOLET_BLUE = "#40456a"
BRICK_RED = "#a84222"  # Wada "Brick Red", a partner of No. 309: reserved for "critical"

# --- surfaces and ink ---------------------------------------------------------------
PAPER = "#f7f4ef"  # page
SURFACE = "#fdfcfa"  # cards, charts
INK = "#1f2433"
INK_2 = "#4b5062"
MUTED = "#8b8d98"
HAIRLINE = "#e4dfd6"
AXIS = "#cdc6b8"

FONT_FAMILY = '"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif'

# --- status (reserved; always paired with an icon or a label) -------------------------
GOOD = "#5f7d3a"
WARNING = GOLDEN_YELLOW
CRITICAL = BRICK_RED

# --- data colors -----------------------------------------------------------------------
# Categorical slots (labels, milestones) in validated order; No. 309's hues lead.
CATEGORICAL = (
    "#006692",  # Vandar Poel's Blue, re-stepped
    "#ec9d53",  # Golden Yellow
    "#767fc8",  # Violet Blue, lighter
    "#858e38",  # Olive Green (Wada partner)
    "#008b9e",  # Cerulean Blue (Wada partner)
    "#de6e28",  # Apricot Orange
    "#ad4682",  # Eupatorium Purple (Wada partner)
)
# Ordinal ramp for priority (validated --ordinal): Critical darkest.
PRIORITY_RAMP = ("#044e6d", "#227197", "#5894b6", "#8cb8d2")
