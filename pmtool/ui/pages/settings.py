"""Settings page [WL-01, WL-07, WL-08, NFR-03, NFR-08, DAT-08] (architecture §9.3).

Placeholder until phase 6.
"""

from __future__ import annotations

from dash import html

from pmtool.ui.pages._placeholder import placeholder

PATH = "/settings"
NAME = "Settings"


def layout(**_kwargs) -> html.Div:
    return placeholder(
        NAME,
        6,
        "Capacity, thresholds, absences, holidays, export, import and archived items.",
    )
