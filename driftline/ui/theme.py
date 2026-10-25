"""Design tokens: colour themes from Sanzo Wada, A Dictionary of Color Combinations.

Each theme is one combination from the dictionary on the same warm paper. Its
colours are used as printed for the interface (navigation, buttons, accents);
a secondary colour too light for white text is darkened in OKLCH until it
reaches 4.5:1. Chart series use the combination's hues re-stepped in OKLCH
into the readable band, filled up with other Wada colours, and validated with
the dataviz palette validator (lightness band, chroma floor, adjacent CVD
ΔE >= 11, normal-vision floor; priority ramps as ordinal). Paper, ink and the
status colours (good / warning / critical) are the same in every theme.

``assets/themes.css`` holds the CSS variables of every theme; it is generated
from this module (``python -m driftline.ui.theme``) and a test keeps it in sync.
The page shell carries ``pm-theme-<key>``, which selects the variables.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from driftline.domain.enums import ColorTheme

# --- surfaces and ink (all themes) -------------------------------------------------
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
WARNING = "#f3a257"  # Wada "Golden Yellow"
CRITICAL = "#a84222"  # Wada "Brick Red"


@dataclass(frozen=True)
class Palette:
    key: ColorTheme
    number: int  # combination number in the dictionary
    name: str
    wada: tuple[tuple[str, str], ...]  # the combination as printed: (colour name, hex)
    # interface
    primary: str  # navbar, primary buttons, links (white text on it)
    primary_hover: str
    primary_active: str
    secondary: str  # secondary buttons, selected segments (white text on it)
    secondary_hover: str
    accent: str  # active tab, "New task" (ink text on it)
    accent_hover: str
    accent_2: str  # brand swatch, capacity cut line
    tint: str  # pale primary: hover fills, empty day bar
    # charts
    categorical: tuple[str, ...]  # labels and milestones, in fixed order
    priority_ramp: tuple[str, ...]  # Critical (darkest) ... Low
    blocked: str  # blocked tasks, capacity shortfall
    today: str  # the "today" line

    @property
    def label(self) -> str:
        return f"No. {self.number} · {self.name}"

    @property
    def in_progress(self) -> str:
        return self.categorical[0]

    @property
    def planned(self) -> str:
        return self.priority_ramp[-1]


THEMES: dict[ColorTheme, Palette] = {
    p.key: p
    for p in (
        Palette(
            key=ColorTheme.NO309,
            number=309,
            name="Harbour",
            wada=(("Golden Yellow", "#f3a257"), ("Apricot Orange", "#f68c50"),
                  ("Violet Blue", "#40456a"), ("Vandar Poel's Blue", "#064f6e")),
            primary="#064f6e", primary_hover="#0a6188", primary_active="#04405a",
            secondary="#40456a", secondary_hover="#4f557f",
            accent="#f3a257", accent_hover="#f68c50", accent_2="#f68c50", tint="#e6eef2",
            categorical=("#006692", "#ec9d53", "#767fc8", "#858e38", "#008b9e", "#de6e28",
                         "#ad4682"),
            priority_ramp=("#044e6d", "#227197", "#5894b6", "#8cb8d2"),
            blocked="#de6e28", today="#f68c50",
        ),
        Palette(
            key=ColorTheme.NO278,
            number=278,
            name="Forest",
            wada=(("Cream Yellow", "#fdbf68"), ("Olive Ocher", "#d6b43e"),
                  ("Cossack Green", "#437742"), ("Dusky Green", "#004f46")),
            primary="#004f46", primary_hover="#1f6359", primary_active="#02433b",
            secondary="#437742", secondary_hover="#578c56",
            accent="#fdbf68", accent_hover="#d6b43e", accent_2="#d6b43e", tint="#e1f3ef",
            categorical=("#038d7f", "#c3a124", "#5182bd", "#bb7125", "#bf7fb4", "#89497b",
                         "#00b49b"),
            priority_ramp=("#025a50", "#257b6f", "#4b9d90", "#83bbb1"),
            blocked="#bb7125", today="#c3a124",
        ),
        Palette(
            key=ColorTheme.NO134,
            number=134,
            name="Plum",
            wada=(("Eosine Pink", "#f37f94"), ("Light Mauve", "#9a72aa"),
                  ("Red Violet", "#59256a")),
            primary="#59256a", primary_hover="#6d397f", primary_active="#4e195e",
            secondary="#8e669d", secondary_hover="#a47bb3",  # Light Mauve, darkened for text
            accent="#f37f94", accent_hover="#e26f85", accent_2="#9a72aa", tint="#f4ebf8",
            categorical=("#7f4a91", "#ef7b90", "#1a699c", "#6b731f", "#c3a124", "#0b939b",
                         "#bb7125"),
            priority_ramp=("#673478", "#875399", "#a974bc", "#bea3c8"),
            blocked="#bb7125", today="#ef7b90",
        ),
        Palette(
            key=ColorTheme.NO328,
            number=328,
            name="Walnut",
            wada=(("Brick Red", "#a84222"), ("Apricot Orange", "#f68c50"),
                  ("Vandyke Brown", "#4b3317"), ("Light Porcelain Green", "#00908a")),
            primary="#4b3317", primary_hover="#5f4529", primary_active="#40290c",
            secondary="#06837d", secondary_hover="#2e9892",  # Porcelain Green, darkened
            accent="#f68c50", accent_hover="#e57c40", accent_2="#00908a", tint="#f8ece1",
            categorical=("#06908a", "#ee8548", "#1a699c", "#6b731f", "#9c70ae", "#b09f36",
                         "#b73f74"),
            priority_ramp=("#644623", "#856541", "#a78561", "#c8a785"),
            blocked="#ee8548", today="#ee8548",
        ),
        Palette(
            key=ColorTheme.NO253,
            number=253,
            name="Slate",
            wada=(("Lemon Yellow", "#f8ed43"), ("Apricot Orange", "#f68c50"),
                  ("Cotinga Purple", "#501345"), ("Slate Color", "#34454c")),
            primary="#34454c", primary_hover="#47585f", primary_active="#2a3a41",
            secondary="#501345", secondary_hover="#652758",
            accent="#f8ed43", accent_hover="#f68c50", accent_2="#f68c50", tint="#e1f2f9",
            categorical=("#057e9f", "#b3a904", "#89497b", "#00b49b", "#6b731f", "#bf7fb4",
                         "#ee8548"),
            priority_ramp=("#235466", "#437386", "#6394a8", "#85b7cb"),
            blocked="#ee8548", today="#ee8548",
        ),
    )
}  # fmt: skip
DEFAULT = ColorTheme.NO309

# The theme of the running app. Driftline serves one person on localhost, so the
# shell sets it from the settings on every page load (``use``) and figure
# builders read it while they run (``active``).
_active: Palette = THEMES[DEFAULT]


def use(key: str | ColorTheme | None) -> Palette:
    """Make ``key`` the active theme; unknown keys fall back to the default."""
    global _active
    try:
        _active = THEMES[ColorTheme(key)]
    except ValueError:
        _active = THEMES[DEFAULT]
    return _active


def active() -> Palette:
    return _active


def shell_class(p: Palette) -> str:
    return f"pm-theme-{p.key.value}"


# --- generated CSS ----------------------------------------------------------------------

CSS_PATH = Path(__file__).parent / "assets" / "themes.css"


def _rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return ", ".join(str(int(h[i : i + 2], 16)) for i in (0, 2, 4))


def css_variables(p: Palette) -> list[str]:
    return [
        f"--pm-primary: {p.primary};",
        f"--pm-primary-rgb: {_rgb(p.primary)};",
        f"--pm-primary-hover: {p.primary_hover};",
        f"--pm-primary-active: {p.primary_active};",
        f"--pm-secondary: {p.secondary};",
        f"--pm-secondary-rgb: {_rgb(p.secondary)};",
        f"--pm-secondary-hover: {p.secondary_hover};",
        f"--pm-accent: {p.accent};",
        f"--pm-accent-hover: {p.accent_hover};",
        f"--pm-accent-2: {p.accent_2};",
        f"--pm-tint-primary: {p.tint};",
        f"--pm-info: {p.categorical[2]};",
        f"--pm-info-rgb: {_rgb(p.categorical[2])};",
    ]


def themes_css() -> str:
    """The content of ``assets/themes.css``: the default on :root, then one block per theme."""
    lines = [
        "/* Generated by `python -m driftline.ui.theme` from ui/theme.py - do not edit. */",
        "",
        f":root {{  /* {THEMES[DEFAULT].label} */",
        *(f"  {v}" for v in css_variables(THEMES[DEFAULT])),
        "}",
    ]
    for p in THEMES.values():
        lines += [
            "",
            f"html:has(.{shell_class(p)}) {{  /* {p.label} */",
            *(f"  {v}" for v in css_variables(p)),
            "}",
        ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    CSS_PATH.write_text(themes_css(), encoding="utf-8")
    print(f"Wrote {CSS_PATH}")
