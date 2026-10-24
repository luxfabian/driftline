"""Timeline page [FUN-11] (architecture §9.3). Placeholder until phase 5."""

from __future__ import annotations

from dash import html

from pmtool.ui.pages._placeholder import placeholder

PATH = "/timeline"
NAME = "Timeline"


def layout(**_kwargs) -> html.Div:
    return placeholder(
        NAME,
        5,
        "Gantt chart with forecast and baseline bars, milestones and a line for today.",
    )
