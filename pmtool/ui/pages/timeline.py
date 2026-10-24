"""Timeline page: Gantt chart [FUN-11, FUN-04, FUN-06/07, FUN-12] (architecture §9.3).

A time window of a week, a month or a year (or everything) with buttons to step
to the previous / next period and back to today. Switches show or hide
milestones and dependency connectors. Click a task bar to open the task detail.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

from pmtool.calc.schedule import dependency_warnings
from pmtool.calc.status import is_overdue
from pmtool.domain.filters import Filter, apply_filter
from pmtool.domain.models import Milestone, Snapshot, Task
from pmtool.services import Services
from pmtool.ui import charts, ids
from pmtool.ui.components import filter_bar
from pmtool.ui.formatting import filter_text
from pmtool.ui.layout import page_header
from pmtool.ui.state import filter_from_store, parse_date

PATH = "/timeline"
NAME = "Timeline"

Unit = Literal["week", "month", "year", "all"]
UNITS: tuple[Unit, ...] = ("week", "month", "year", "all")
DEFAULT_UNIT: Unit = "month"


# --- time window (pure) ------------------------------------------------------------------


def window(anchor: date, unit: Unit) -> tuple[date, date] | None:
    """First and last day of the period containing ``anchor``; None for "all"."""
    if unit == "week":
        first = anchor - timedelta(days=anchor.weekday())
        return first, first + timedelta(days=6)
    if unit == "month":
        first = anchor.replace(day=1)
        return first, _add_months(first, 1) - timedelta(days=1)
    if unit == "year":
        return date(anchor.year, 1, 1), date(anchor.year, 12, 31)
    return None


def shift(anchor: date, unit: Unit, steps: int) -> date:
    """The anchor moved by ``steps`` periods (negative = back)."""
    if unit == "week":
        return anchor + timedelta(weeks=steps)
    if unit == "month":
        return _add_months(anchor.replace(day=1), steps)
    if unit == "year":
        return anchor.replace(year=anchor.year + steps, month=1, day=1)
    return anchor


def period_label(anchor: date, unit: Unit) -> str:
    span = window(anchor, unit)
    if span is None:
        return "All dates"
    first, last = span
    if unit == "week":
        return f"Week {first.isocalendar().week} · {first:%d %b} – {last:%d %b %Y}"
    if unit == "month":
        return f"{first:%B %Y}"
    return f"{first:%Y}"


def _add_months(d: date, months: int) -> date:
    """First of the month ``months`` after ``d``'s month (d must be a 1st)."""
    index = d.year * 12 + d.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _in_window(t: Task, first: date, last: date) -> bool:
    """Forecast or baseline bar touches the window."""
    return (t.forecast_start <= last and t.forecast_end >= first) or (
        t.baseline_start <= last and t.baseline_end >= first
    )


def _ms_in_window(m: Milestone, first: date, last: date) -> bool:
    return first <= m.forecast_date <= last or first <= m.baseline_date <= last


# --- figure ------------------------------------------------------------------------


def timeline_figure(
    snap: Snapshot,
    f: Filter,
    today: date,
    show_milestones: bool,
    show_dependencies: bool = False,
    span: tuple[date, date] | None = None,
) -> go.Figure:
    """Filtered tasks; milestones = the filtered ones, or all shown ones if none chosen.

    With ``span`` only tasks and milestones that touch it are shown, and the axis
    is fixed to it.
    """
    tasks = apply_filter(snap.tasks, f)
    milestones: list[Milestone] = []
    if show_milestones:
        milestones = [
            m for m in snap.milestones
            if (not f.milestone_ids or m.id in f.milestone_ids)
            and (f.include_archived or not m.is_archived)
        ]  # fmt: skip
    if span is not None:
        tasks = [t for t in tasks if _in_window(t, *span)]
        milestones = [m for m in milestones if _ms_in_window(m, *span)]
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
        window=span,
    )


# --- layout ------------------------------------------------------------------------


def layout(**_kwargs) -> html.Div:
    def switch(label, component_id, value):
        return dbc.Switch(id=component_id, label=label, value=value, persistence=True,
                          persistence_type="session", className="mb-0 ms-2")  # fmt: skip

    def step(label, component_id, title):
        return dbc.Button(label, id=component_id, size="sm", color="secondary", outline=True,
                          title=title)  # fmt: skip

    period = html.Div(
        [
            dbc.RadioItems(
                id=ids.TIMELINE_UNIT,
                options=[{"label": u.capitalize(), "value": u} for u in UNITS],
                value=DEFAULT_UNIT,
                inline=True,
                inputClassName="btn-check",
                labelClassName="btn btn-outline-secondary btn-sm",
                labelCheckedClassName="active",
                className="pm-seg",
                persistence=True,
                persistence_type="session",
            ),
            html.Div(
                [
                    step("‹", ids.TIMELINE_PREV, "Previous period"),
                    step("Today", ids.TIMELINE_TODAY, "Back to the current period"),
                    step("›", ids.TIMELINE_NEXT, "Next period"),
                ],
                className="btn-group",
            ),
        ],
        className="d-flex gap-2 align-items-center",
    )
    return html.Div(
        [
            page_header(
                NAME,
                ids.TIMELINE_PERIOD,
                [
                    period,
                    switch("Milestones", ids.TIMELINE_MILESTONES, True),
                    switch("Dependencies", ids.TIMELINE_DEPENDENCIES, True),
                ],
            ),
            dcc.Store(id=ids.TIMELINE_ANCHOR, storage_type="session"),
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


# --- callbacks ---------------------------------------------------------------------


def register_callbacks(app: Dash, services: Services) -> None:
    clock = services.tasks.clock

    @app.callback(
        Output(ids.TIMELINE_ANCHOR, "data"),
        Input(ids.TIMELINE_PREV, "n_clicks"),
        Input(ids.TIMELINE_NEXT, "n_clicks"),
        Input(ids.TIMELINE_TODAY, "n_clicks"),
        State(ids.TIMELINE_ANCHOR, "data"),
        State(ids.TIMELINE_UNIT, "value"),
        prevent_initial_call=True,
    )
    def navigate(_prev, _next, _today, anchor, unit):
        if not ctx.triggered or not ctx.triggered[0]["value"]:
            return no_update
        if ctx.triggered_id == ids.TIMELINE_TODAY:
            return clock.today().isoformat()
        steps = -1 if ctx.triggered_id == ids.TIMELINE_PREV else 1
        current = parse_date(anchor) or clock.today()
        return shift(current, _unit(unit), steps).isoformat()

    @app.callback(
        Output(ids.TIMELINE_GRAPH, "figure"),
        Output(ids.TIMELINE_PERIOD, "children"),
        Output(ids.TIMELINE_PREV, "disabled"),
        Output(ids.TIMELINE_NEXT, "disabled"),
        Input(ids.DATA_VERSION, "data"),
        Input(ids.FILTER, "data"),
        Input(ids.TIMELINE_MILESTONES, "value"),
        Input(ids.TIMELINE_DEPENDENCIES, "value"),
        Input(ids.TIMELINE_ANCHOR, "data"),
        Input(ids.TIMELINE_UNIT, "value"),
    )
    def refresh(_version, filter_data, show_milestones, show_dependencies, anchor, unit):
        f = filter_from_store(filter_data)
        unit = _unit(unit)
        current = parse_date(anchor) or clock.today()
        snap = services.snapshot.load(include_archived=f.include_archived)
        figure = timeline_figure(snap, f, clock.today(), bool(show_milestones),
                                 bool(show_dependencies), window(current, unit))  # fmt: skip
        no_steps = unit == "all"
        return figure, period_label(current, unit), no_steps, no_steps

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


def _unit(value) -> Unit:
    return value if value in UNITS else DEFAULT_UNIT


def clicked_task_id(click: dict | None) -> int | None:
    """Task id from a Gantt click; milestones (negative ids) and outlines give None."""
    for point in (click or {}).get("points", []):
        data = point.get("customdata")
        if isinstance(data, list) and data and isinstance(data[0], int) and data[0] > 0:
            return data[0]
    return None
