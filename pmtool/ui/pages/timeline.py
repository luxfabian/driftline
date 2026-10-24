"""Timeline page: Gantt chart [FUN-11, FUN-04, FUN-12] (architecture §9.3).

Click a task bar to open the task detail.
"""

from __future__ import annotations

from datetime import date

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html, no_update

from pmtool.calc.status import is_overdue
from pmtool.domain.filters import Filter, apply_filter
from pmtool.domain.models import Snapshot
from pmtool.services import Services
from pmtool.ui import charts, ids
from pmtool.ui.formatting import filter_text
from pmtool.ui.state import filter_from_store

PATH = "/timeline"
NAME = "Timeline"


def timeline_figure(snap: Snapshot, f: Filter, today: date, show_milestones: bool) -> go.Figure:
    """Filtered tasks; milestones = the filtered ones, or all shown ones if none chosen."""
    tasks = apply_filter(snap.tasks, f)
    milestones = []
    if show_milestones:
        milestones = [
            m for m in snap.milestones
            if (not f.milestone_ids or m.id in f.milestone_ids)
            and (f.include_archived or not m.is_archived)
        ]  # fmt: skip
    return charts.build_gantt(
        tasks,
        milestones,
        today,
        filter_text(snap, f),
        risk_ids={t.id for t in tasks if t.at_risk},
        overdue_ids={t.id for t in tasks if is_overdue(t, today)},
    )


def layout(**_kwargs) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.H4(NAME, className="mb-0"),
                    dbc.Switch(
                        id=ids.TIMELINE_MILESTONES,
                        label="Show milestones",
                        value=True,
                        persistence=True,
                        persistence_type="session",
                    ),
                ],  # fmt: skip
                className="d-flex justify-content-between align-items-center mb-2",
            ),
            html.P(
                "Filled bars: forecast (color = status, hatched = blocked). Outlines: "
                "baseline. ◆ forecast, ◇ baseline of milestones. Click a bar for details.",
                className="text-muted small mb-1",
            ),
            dcc.Graph(id=ids.TIMELINE_GRAPH, config={"displaylogo": False}),
        ]
    )


def register_callbacks(app: Dash, services: Services) -> None:
    clock = services.tasks.clock

    @app.callback(
        Output(ids.TIMELINE_GRAPH, "figure"),
        Input(ids.DATA_VERSION, "data"),
        Input(ids.FILTER, "data"),
        Input(ids.TIMELINE_MILESTONES, "value"),
    )
    def refresh(_version, filter_data, show_milestones):
        f = filter_from_store(filter_data)
        snap = services.snapshot.load(include_archived=f.include_archived)
        return timeline_figure(snap, f, clock.today(), bool(show_milestones))

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
