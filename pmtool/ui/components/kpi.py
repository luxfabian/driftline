"""Stat tiles for the dashboard and workload pages [WL-07, WL-08].

A status color never stands alone: the load tile always pairs it with an icon
and a word (OK / Tight / Overloaded).
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from pmtool.domain.models import Settings
from pmtool.ui.charts import INK, INK_2, MUTED, STATUS_CRITICAL, STATUS_GOOD, STATUS_WARNING

LEVELS = {  # level -> (color, icon, word)
    "green": (STATUS_GOOD, "✓", "OK"),
    "amber": (STATUS_WARNING, "!", "Tight"),
    "red": (STATUS_CRITICAL, "✕", "Overloaded"),
    "na": (MUTED, "–", "n/a (no capacity)"),
}


def stat_tile(label: str, value: str, note: str | None = None, accent: str | None = None):
    body = [
        html.Div(label, className="small", style={"color": INK_2}),
        html.Div(value, className="fs-3 fw-semibold", style={"color": INK}),
    ]
    if note:
        body.append(html.Div(note, className="small", style={"color": MUTED}))
    style = {"borderLeft": f"4px solid {accent}"} if accent else {}
    return dbc.Card(dbc.CardBody(body, className="py-2"), className="h-100", style=style)


def load_tile(ratio: float | None, level: str, horizon_weeks: int, settings: Settings):
    color, icon, word = LEVELS[level]
    value = "n/a" if ratio is None else f"{ratio:.0%}"
    thresholds = f"green < {settings.load_green_max:.0%} · amber ≤ {settings.load_amber_max:.0%}"
    return stat_tile(
        f"Load ratio, next {horizon_weeks} week{'s' if horizon_weeks != 1 else ''}",
        value,
        note=html.Span(
            [
                html.Span(f"{icon} {word}", style={"color": INK, "fontWeight": 600}),
                f" · {thresholds}",
            ]
        ),
        accent=color,
    )
