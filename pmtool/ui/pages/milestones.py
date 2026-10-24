"""Milestones page [DAT-05, SCH-03..SCH-05] (architecture §9.3). Placeholder until phase 5."""

from __future__ import annotations

from dash import html

from pmtool.ui.pages._placeholder import placeholder

PATH = "/milestones"
NAME = "Milestones"


def layout(**_kwargs) -> html.Div:
    return placeholder(
        NAME,
        5,
        "Milestone table with variance and warnings, plus the milestone trend analysis chart.",
    )
