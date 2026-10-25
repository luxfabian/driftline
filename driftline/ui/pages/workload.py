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

from driftline.calc.calendar import CalendarContext
from driftline.calc.status import is_open
from driftline.calc.workload import (
    NO_LABEL,
    cumulative_curves,
    daily_allocation,
    horizon_end,
    load_level,
    load_ratio,
    weekly_capacity,
    weekly_load,
)
from driftline.domain.filters import Filter, apply_filter
from driftline.domain.models import Snapshot
from driftline.services import Services
from driftline.ui import charts, ids
from driftline.ui.components import filter_bar
from driftline.ui.components.kpi import load_tile
from driftline.ui.formatting import filter_text
from driftline.ui.layout import page_header
from driftline.ui.state import filter_from_store

PATH = "/workload"
NAME = "Workload"
NO_LABEL_COLOR = "#cfcbd6"


@dataclass(frozen=True)
class WorkloadData:
    curves: pd.DataFrame
    weekly: pd.DataFrame
    capacity: pd.DataFrame
    ratio: float | None
    level: str
    colors: dict[str, str]


def workload_filter(f: Filter) -> Filter:
    """The part of the filter that changes demand: which work, not its status or dates.

    Demand is always the open work (WL-03, WL-05) over the chosen horizon.
    """
    return Filter(labels=f.labels, label_mode=f.label_mode, priorities=f.priorities,
                  milestone_ids=f.milestone_ids, at_risk_only=f.at_risk_only)  # fmt: skip


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
        colors = charts.categorical_colors(colored_labels(snap))
        colors = {k: v for k, v in colors.items() if v != charts.OTHER_COLOR}
        weekly = charts.fold_groups(weekly, {*colors, NO_LABEL})
        colors |= {NO_LABEL: NO_LABEL_COLOR, charts.OTHER: charts.OTHER_COLOR}
    else:
        colors = charts.priority_colors()
    ratio = load_ratio(tasks, today, horizon_weeks, ctx)
    return WorkloadData(
        curves=cumulative_curves(tasks, today, end, ctx),
        weekly=weekly,
        capacity=weekly_capacity(today, end, ctx),
        ratio=ratio,
        level=load_level(ratio, snap.settings),
        colors=colors,
    )


def colored_labels(snap: Snapshot) -> list[str]:
    """Labels that get their own color, alphabetically; any others share "Other".

    With more labels than color slots, the ones with the most open hours keep a
    color. This is decided on all open work, not the filtered view, so filtering
    never repaints the chart.
    """
    names = {lb.id: lb.name for lb in snap.labels}
    if len(names) <= len(charts.categorical()):
        return sorted(names.values(), key=str.lower)
    hours: dict[str, float] = dict.fromkeys(names.values(), 0.0)
    for t in snap.tasks:
        if is_open(t):
            for i in t.label_ids:
                hours[names[i]] += t.remaining_effort_h
    biggest = sorted(hours, key=lambda n: (-hours[n], n.lower()))[: len(charts.categorical()) - 1]
    return sorted(biggest, key=str.lower)


def layout(**_kwargs) -> html.Div:
    controls = dbc.Row(
        [
            dbc.Col(
                [
                    dbc.Label("Horizon (weeks)", className="pm-hint mb-0"),
                    dcc.Slider(
                        id=ids.WL_HORIZON, min=1, max=12, step=1, value=None,
                        marks={i: str(i) for i in (1, 2, 4, 6, 8, 10, 12)},
                        persistence=True, persistence_type="session",
                    ),
                ],
                lg=5,
            ),
            dbc.Col(
                [
                    dbc.Label("Weekly load by", className="pm-hint mb-1 d-block"),
                    dbc.RadioItems(
                        id=ids.WL_GROUP_BY,
                        options=[{"label": "Priority", "value": "priority"},
                                 {"label": "Label", "value": "label"}],
                        value="priority", inline=True,
                        inputClassName="btn-check",
                        labelClassName="btn btn-outline-secondary btn-sm",
                        labelCheckedClassName="active", className="pm-seg",
                        persistence=True, persistence_type="session",
                    ),
                ],
                lg=3,
            ),
            dbc.Col(html.Div(id=ids.WL_RATIO), lg=4),
        ],
        className="g-3 align-items-center mb-3",
    )  # fmt: skip
    return html.Div(
        [
            page_header(NAME),
            filter_bar.layout("workload", filter_bar.WORKLOAD_FIELDS),
            controls,
            html.Div(dcc.Graph(id=ids.WL_CUMULATIVE, config={"displaylogo": False}),
                     className="pm-panel"),
            html.Div(dcc.Graph(id=ids.WL_WEEKLY, config={"displaylogo": False}),
                     className="pm-panel"),
            html.P(
                "Cumulative demand: whether the work fits by its due dates (overdue work "
                "counts as due today); the upper, warm part of a bar is the shortfall. Weekly "
                "load: remaining effort spread over the working days from each task's start, "
                "so it shows where the peaks are.",
                className="pm-hint",
            ),
        ]
    )  # fmt: skip


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
        f = workload_filter(filter_from_store(filter_data))
        snap = services.snapshot.load()
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
