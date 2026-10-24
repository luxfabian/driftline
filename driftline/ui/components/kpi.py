"""Stat tiles for the dashboard and workload pages [WL-07, WL-08].

A status color never stands alone: the load tile always pairs it with an icon
and a word (OK / Tight / Overloaded). The color is a thin top edge, the
number itself stays in ink.
"""

from __future__ import annotations

from typing import Any

import dash_bootstrap_components as dbc
from dash import html

from driftline.domain.models import Settings
from driftline.ui.theme import CRITICAL, GOOD, HAIRLINE, INK, MUTED, WARNING

LEVELS = {  # level -> (color, icon, word)
    "green": (GOOD, "✓", "OK"),
    "amber": (WARNING, "!", "Tight"),
    "red": (CRITICAL, "✕", "Overloaded"),
    "na": (MUTED, "–", "n/a (no capacity)"),
}


def stat_tile(label: str, value: str, note: Any = None, accent: str | None = None) -> dbc.Card:
    body = [html.Div(label, className="pm-tile-label"), html.Div(value, className="pm-tile-value")]
    if note:
        body.append(html.Div(note, className="pm-tile-note"))
    return dbc.Card(
        dbc.CardBody(body),
        className="pm-tile pm-tile-accent",
        style={"borderTopColor": accent or HAIRLINE},
    )


def load_tile(ratio: float | None, level: str, horizon_weeks: int, settings: Settings):
    color, icon, word = LEVELS[level]
    value = "n/a" if ratio is None else f"{ratio:.0%}"
    thresholds = f"green < {settings.load_green_max:.0%} · amber ≤ {settings.load_amber_max:.0%}"
    return stat_tile(
        f"Load, next {horizon_weeks} week{'s' if horizon_weeks != 1 else ''}",
        value,
        note=html.Span(
            [html.Span(f"{icon} {word}", style={"color": INK, "fontWeight": 600}),
             f" · {thresholds}"]
        ),
        accent=color,
    )  # fmt: skip
