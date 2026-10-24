"""Workload page [WL-03..WL-07] (architecture §9.3).

Chart 1 shows WHETHER the work fits (cumulative demand vs. capacity), chart 2
shows WHERE the peaks are (weekly spread from each task's start date).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import dash_bootstrap_components as dbc
import pandas as pd
from dash import Dash, Input, Output, dcc, html

from pmtool.calc.calendar import CalendarContext
from pmtool.calc.workload import (
    NO_LABEL,
    cumulative_curves,
    daily_allocation,
    horizon_end,
    load_level,
    load_ratio,
    weekly_capacity,
    weekly_load,
)
from pmtool.domain.filters import Filter, apply_filter
from pmtool.domain.models import Snapshot
from pmtool.services import Services
from pmtool.ui import charts, ids
from pmtool.ui.components.kpi import load_tile
from pmtool.ui.formatting import filter_text
from pmtool.ui.state import filter_from_store

PATH = "/workload"
NAME = "Workload"
NO_LABEL_COLOR = "#c3c2b7"


@dataclass(frozen=True)
class WorkloadData:
    curves: pd.DataFrame
    weekly: pd.DataFrame
    capacity: pd.DataFrame
    ratio: float | None
    level: str
    colors: dict[str, str]


def workload_data(
    snap: Snapshot,
    f: Filter,
    today: date,
    horizon_weeks: int,
    group_by: Literal["priority", "label"],
) -> WorkloadData:
    """All numbers for the page from one snapshot (pure)."""
    tasks = apply_filter(snap.tasks, f)  # FUN-10
    ctx = CalendarContext.from_snapshot(snap)
    end = horizon_end(today, horizon_weeks)
    allocation = daily_allocation(tasks, today, end, ctx)
    label_names = {lb.id: lb.name for lb in snap.labels}
    weekly = weekly_load(allocation, tasks, group_by, ctx, label_names)
    if group_by == "label":
        # Colors keyed by every label (stable across filters); >8 labels fold to "Other".
        colors = charts.categorical_colors(sorted(label_names.values(), key=str.lower))
        colors = {k: v for k, v in colors.items() if v != charts.OTHER_COLOR}
        weekly = charts.fold_groups(weekly, {*colors, NO_LABEL})
        colors |= {NO_LABEL: NO_LABEL_COLOR, charts.OTHER: charts.OTHER_COLOR}
    else:
        colors = dict(charts.PRIORITY_COLORS)
    ratio = load_ratio(tasks, today, horizon_weeks, ctx)
    return WorkloadData(
        curves=cumulative_curves(tasks, today, end, ctx),
        weekly=weekly,
        capacity=weekly_capacity(today, end, ctx),
        ratio=ratio,
        level=load_level(ratio, snap.settings),
        colors=colors,
    )


def layout(**_kwargs) -> html.Div:
    controls = dbc.Row(
        [
            dbc.Col(
                [
                    dbc.Label("Horizon (weeks)", className="small mb-0"),
                    dcc.Slider(
                        id=ids.WL_HORIZON, min=1, max=12, step=1, value=None,
                        marks={i: str(i) for i in range(1, 13)},
                        persistence=True, persistence_type="session",
                    ),
                ],
                md=6,
            ),
            dbc.Col(
                [
                    dbc.Label("Color weekly bars by", className="small mb-0"),
                    dbc.RadioItems(
                        id=ids.WL_GROUP_BY,
                        options=[{"label": "Priority", "value": "priority"},
                                 {"label": "Label", "value": "label"}],
                        value="priority", inline=True,
                        persistence=True, persistence_type="session",
                    ),
                ],
                md=3,
            ),
            dbc.Col(html.Div(id=ids.WL_RATIO), md=3),
        ],
        className="g-3 align-items-center mb-2",
    )  # fmt: skip
    return html.Div(
        [
            html.H4(NAME),
            controls,
            dcc.Graph(id=ids.WL_CUMULATIVE, config={"displaylogo": False}),
            dcc.Graph(id=ids.WL_WEEKLY, config={"displaylogo": False}),
            html.P(
                "The cumulative chart shows whether the work fits by its due dates (overdue "
                "work counts as due today). The weekly chart spreads remaining effort over "
                "the working days from each task's start, so it shows where the peaks are.",
                className="text-muted small",
            ),
        ]
    )


def register_callbacks(app: Dash, services: Services) -> None:
    clock = services.tasks.clock

    @app.callback(
        Output(ids.WL_HORIZON, "value"),
        Input(ids.WL_HORIZON, "id"),
        Input(ids.WL_HORIZON, "value"),
    )
    def default_horizon(_id, value):
        """Start from the configured default horizon (WL-07)."""
        if value:
            return value
        return services.settings.get().default_horizon_weeks

    @app.callback(
        Output(ids.WL_CUMULATIVE, "figure"),
        Output(ids.WL_WEEKLY, "figure"),
        Output(ids.WL_RATIO, "children"),
        Input(ids.DATA_VERSION, "data"),
        Input(ids.FILTER, "data"),
        Input(ids.WL_HORIZON, "value"),
        Input(ids.WL_GROUP_BY, "value"),
    )
    def refresh(_version, filter_data, horizon, group_by):
        f = filter_from_store(filter_data)
        snap = services.snapshot.load(include_archived=f.include_archived)
        horizon = int(horizon or snap.settings.default_horizon_weeks)
        group_by = "label" if group_by == "label" else "priority"
        data = workload_data(snap, f, clock.today(), horizon, group_by)
        text = filter_text(snap, f)
        return (
            charts.build_cumulative(data.curves, text),
            charts.build_weekly_load(data.weekly, data.capacity, group_by.capitalize(), text,
                                     colors=data.colors),
            load_tile(data.ratio, data.level, horizon, snap.settings),
        )  # fmt: skip
