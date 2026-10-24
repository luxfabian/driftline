"""Timeline page: Gantt chart [FUN-11, FUN-04, FUN-06/07, FUN-12] (architecture §9.3).

Switches show or hide milestones and dependency connectors. Click a task bar
to open the task detail.
"""

from __future__ import annotations

from datetime import date

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html, no_update

from pmtool.calc.schedule import dependency_warnings
from pmtool.calc.status import is_overdue
from pmtool.domain.filters import Filter, apply_filter
from pmtool.domain.models import Snapshot
from pmtool.services import Services
from pmtool.ui import charts, ids
from pmtool.ui.components import filter_bar
from pmtool.ui.formatting import filter_text
from pmtool.ui.layout import page_header
from pmtool.ui.state import filter_from_store

PATH = "/timeline"
NAME = "Timeline"


def timeline_figure(
    snap: Snapshot,
    f: Filter,
    today: date,
    show_milestones: bool,
    show_dependencies: bool = False,
) -> go.Figure:
    """Filtered tasks; milestones = the filtered ones, or all shown ones if none chosen."""
    tasks = apply_filter(snap.tasks, f)
    milestones = []
    if show_milestones:
        milestones = [
            m for m in snap.milestones
            if (not f.milestone_ids or m.id in f.milestone_ids)
            and (f.include_archived or not m.is_archived)
        ]  # fmt: skip
    links: list[tuple[int, int, bool]] = []
    if show_dependencies:
        late = dependency_warnings(snap.tasks)  # FUN-07, checked against all active tasks
        links = [
            (p, t.id, p in late.get(t.id, ())) for t in tasks for p in sorted(t.predecessor_ids)
        ]
    return charts.build_gantt(
        tasks,
        milestones,
        today,
        filter_text(snap, f),
        risk_ids={t.id for t in tasks if t.at_risk},
        overdue_ids={t.id for t in tasks if is_overdue(t, today)},
        dependencies=links,
    )


def layout(**_kwargs) -> html.Div:
    def switch(label, component_id, value):
        return dbc.Switch(id=component_id, label=label, value=value, persistence=True,
                          persistence_type="session", className="mb-0 ms-3")  # fmt: skip

    return html.Div(
        [
            page_header(
                NAME,
                actions=[
                    switch("Milestones", ids.TIMELINE_MILESTONES, True),
                    switch("Dependencies", ids.TIMELINE_DEPENDENCIES, True),
                ],
            ),
            filter_bar.layout("timeline"),
            html.Div(
                dcc.Graph(id=ids.TIMELINE_GRAPH, config={"displaylogo": False}),
                className="pm-panel",
            ),
            html.P(
                "Filled bars: forecast (color = status, hatched = blocked). Outlines: baseline. "
                "◆ forecast, ◇ baseline of milestones. Arrows run from a task's end to the "
                "start of the task that depends on it; red ones start before it ends. "
                "Click a bar for details.",
                className="pm-hint",
            ),
        ]
    )


def register_callbacks(app: Dash, services: Services) -> None:
    clock = services.tasks.clock

    @app.callback(
        Output(ids.TIMELINE_GRAPH, "figure"),
        Input(ids.DATA_VERSION, "data"),
        Input(ids.FILTER, "data"),
        Input(ids.TIMELINE_MILESTONES, "value"),
        Input(ids.TIMELINE_DEPENDENCIES, "value"),
    )
    def refresh(_version, filter_data, show_milestones, show_dependencies):
        f = filter_from_store(filter_data)
        snap = services.snapshot.load(include_archived=f.include_archived)
        return timeline_figure(snap, f, clock.today(), bool(show_milestones),
                               bool(show_dependencies))  # fmt: skip

    @app.callback(
        Output(ids.SELECTED_TASK, "data", allow_duplicate=True),
        Output(ids.DETAIL, "is_open", allow_duplicate=True),
        Input(ids.TIMELINE_GRAPH, "clickData"),
        prevent_initial_call=True,
    )
    def open_detail(click):
        task_id = clicked_task_id(click)
        if task_id is None:
            return no_update, no_update
        return task_id, True


def clicked_task_id(click: dict | None) -> int | None:
    """Task id from a Gantt click; milestones (negative ids) and outlines give None."""
    for point in (click or {}).get("points", []):
        data = point.get("customdata")
        if isinstance(data, list) and data and isinstance(data[0], int) and data[0] > 0:
            return data[0]
    return None
