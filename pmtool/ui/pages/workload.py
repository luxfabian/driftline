"""Workload page [WL-03..WL-07] (architecture §9.3). Placeholder until phase 5."""

from __future__ import annotations

from dash import html

from pmtool.ui.pages._placeholder import placeholder

PATH = "/workload"
NAME = "Workload"


def layout(**_kwargs) -> html.Div:
    return placeholder(
        NAME,
        5,
        "Cumulative demand vs. capacity and weekly load charts with the load ratio.",
    )
