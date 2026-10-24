"""Dashboard page [WL-07, WL-08, FUN-12, SCH-05, SCH-06, FUN-07] (architecture §9.3).

Placeholder until phase 5.
"""

from __future__ import annotations

from dash import html

from pmtool.ui.pages._placeholder import placeholder

PATH = "/"
NAME = "Dashboard"


def layout(**_kwargs) -> html.Div:
    return placeholder(
        NAME,
        5,
        "KPI cards (load ratio, overdue, at risk, blocked, stale) and lists of delayed "
        "items and warnings.",
    )
