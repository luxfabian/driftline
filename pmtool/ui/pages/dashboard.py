"""Dashboard [WL-07, WL-08, FUN-12, SCH-05, SCH-06, FUN-07] (architecture §9.3).

An overview of all open work, without a filter (the filter lives on Tasks,
Timeline and Workload). ``dashboard_data`` still takes a filter: KPIs and the
delayed list follow it, while milestone and dependency warnings are checked
against all active tasks (a predecessor outside the filter can still be late).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, html

from pmtool.calc.calendar import CalendarContext
from pmtool.calc.schedule import (
    DelayItem,
    dependency_cycles,
    dependency_warnings,
    milestone_task_warnings,
    top_delayed,
)
from pmtool.calc.status import is_open, is_overdue, is_stale
from pmtool.calc.workload import load_level, load_ratio
from pmtool.domain.enums import TaskStatus
from pmtool.domain.filters import Filter, apply_filter
from pmtool.domain.models import Milestone, Snapshot, Task
from pmtool.services import Services
from pmtool.ui import charts, ids
from pmtool.ui.components.kpi import load_tile, stat_tile
from pmtool.ui.layout import page_header

PATH = "/"
NAME = "Dashboard"


@dataclass(frozen=True)
class DashboardData:
    ratio: float | None
    level: str
    horizon_weeks: int
    overdue: int
    at_risk: int
    blocked: int
    stale: int
    delayed: list[DelayItem]
    milestone_warnings: list[tuple[Milestone, date]]  # milestone, latest task end
    dependency_warnings: list[tuple[Task, list[Task]]]  # task, late predecessors
    cycles: list[list[Task]]


def dashboard_data(snap: Snapshot, f: Filter, today: date, now: datetime) -> DashboardData:
    tasks = apply_filter(snap.tasks, f)
    open_tasks = [t for t in tasks if is_open(t)]
    active = [t for t in snap.tasks if not t.is_archived]
    by_id = {t.id: t for t in snap.tasks}
    ms_by_id = {m.id: m for m in snap.milestones}
    horizon = snap.settings.default_horizon_weeks
    ratio = load_ratio(tasks, today, horizon, CalendarContext.from_snapshot(snap))

    shown = {t.id for t in tasks}
    late = dependency_warnings(active)
    milestones = [m for m in snap.milestones if not f.milestone_ids or m.id in f.milestone_ids]
    ms_warn = milestone_task_warnings(milestones, active)
    return DashboardData(
        ratio=ratio,
        level=load_level(ratio, snap.settings),
        horizon_weeks=horizon,
        overdue=sum(is_overdue(t, today) for t in tasks),
        at_risk=sum(t.at_risk for t in open_tasks),
        blocked=sum(t.status is TaskStatus.BLOCKED for t in open_tasks),
        stale=sum(is_stale(t, now, snap.settings.stale_after_days) for t in tasks),
        delayed=top_delayed(tasks, milestones, snap.settings.top_delayed_n),
        milestone_warnings=sorted(
            ((ms_by_id[i], end) for i, end in ms_warn.items()),
            key=lambda pair: (pair[0].forecast_date, pair[0].id),
        ),
        dependency_warnings=[
            (by_id[t_id], [by_id[p] for p in preds])
            for t_id, preds in sorted(late.items())
            if t_id in shown
        ],
        cycles=[[by_id[i] for i in cycle] for cycle in dependency_cycles(active)],
    )


# --- layout ------------------------------------------------------------------------


def layout(**_kwargs) -> html.Div:
    return html.Div(
        [
            page_header(NAME, ids.DASH_FILTER_TEXT),
            html.Div(id=ids.DASH_KPIS, className="mb-4"),
            dbc.Row(
                [
                    dbc.Col(_card("Most delayed", ids.DASH_DELAYED), lg=6),
                    dbc.Col(
                        [
                            _card("Milestone warnings", ids.DASH_MS_WARNINGS),
                            _card("Dependency warnings", ids.DASH_DEP_WARNINGS),
                        ],
                        lg=6,
                    ),
                ],
                className="g-3",
            ),
        ]
    )


def _card(title: str, body_id: str) -> dbc.Card:
    return dbc.Card(
        [dbc.CardHeader(title, className="fw-semibold"), dbc.CardBody(id=body_id)],
        className="mb-3",
    )


def kpi_row(data: DashboardData, snap: Snapshot) -> dbc.Row:
    s = snap.settings
    tiles = [
        load_tile(data.ratio, data.level, data.horizon_weeks, s),
        stat_tile("Overdue", str(data.overdue), "forecast end before today",
                  charts.STATUS_CRITICAL if data.overdue else None),
        stat_tile("At risk", str(data.at_risk), "⚠ flagged tasks",
                  charts.STATUS_WARNING if data.at_risk else None),
        stat_tile("Blocked", str(data.blocked), "cannot proceed",
                  charts.STATUS_CRITICAL if data.blocked else None),
        stat_tile("Stale", str(data.stale), f"not reviewed for {s.stale_after_days}+ days",
                  charts.STATUS_WARNING if data.stale else None),
    ]  # fmt: skip
    return dbc.Row([dbc.Col(t, xs=12, sm=6, xl=True) for t in tiles], className="g-3")


def task_link(t: Task, key: str, text: str | None = None) -> dbc.Button:
    return dbc.Button(
        text or f"#{t.id} {t.title}",
        id=ids.open_task(t.id, key),
        color="link",
        size="sm",
        className="p-0 text-start align-baseline",
    )


def delayed_list(items: list[DelayItem], tasks: dict[int, Task]):
    if not items:
        return html.P("Nothing is behind its baseline.", className="text-muted small mb-0")
    rows = []
    for item in items:
        if item.kind == "task" and item.id in tasks:
            name = task_link(tasks[item.id], "delayed")
        else:
            name = html.Span(f"◆ {item.name}")
        rows.append(
            html.Tr(
                [
                    html.Td(name),
                    html.Td(item.baseline.isoformat(), className="text-muted"),
                    html.Td(item.forecast.isoformat()),
                    html.Td(f"+{item.variance_d} d", className="text-end fw-semibold"),
                ]
            )
        )
    head = html.Thead(html.Tr([html.Th("Item"), html.Th("Baseline"), html.Th("Forecast"),
                               html.Th("Variance", className="text-end")]))  # fmt: skip
    return dbc.Table([head, html.Tbody(rows)], size="sm", className="small mb-0")


def milestone_warning_list(items: list[tuple[Milestone, date]]):
    if not items:
        return html.P("All milestones are later than their open tasks.",
                      className="text-muted small mb-0")  # fmt: skip
    return html.Ul(
        [
            html.Li(
                f"◆ {m.name}: forecast {m.forecast_date.isoformat()}, but linked open "
                f"tasks end {end.isoformat()} (+{(end - m.forecast_date).days} d)"
            )
            for m, end in items
        ],  # fmt: skip
        className="small mb-0",
    )


def dependency_warning_list(items: list[tuple[Task, list[Task]]], cycles: list[list[Task]]):
    if not items and not cycles:
        return html.P("No task starts before its predecessors end.",
                      className="text-muted small mb-0")  # fmt: skip
    entries = [
        html.Li(
            [
                task_link(t, f"dep{i}"),
                " starts ",
                t.forecast_start.isoformat(),
                ", before ",
                *_join([task_link(p, f"dep{i}-{j}", f"#{p.id}") for j, p in enumerate(preds)]),
                " end",
                "s" if len(preds) == 1 else "",
            ]
        )  # fmt: skip
        for i, (t, preds) in enumerate(items)
    ]
    entries += [
        html.Li(["Dependency loop: ",
                 *_join([task_link(t, f"loop{i}-{j}", f"#{t.id}") for j, t in enumerate(cycle)])])
        for i, cycle in enumerate(cycles)
    ]  # fmt: skip
    return html.Ul(entries, className="small mb-0")


def _join(parts: list) -> list:
    result: list = []
    for i, part in enumerate(parts):
        if i:
            result.append(", ")
        result.append(part)
    return result


# --- callbacks ---------------------------------------------------------------------


def register_callbacks(app: Dash, services: Services) -> None:
    clock = services.tasks.clock

    @app.callback(
        Output(ids.DASH_FILTER_TEXT, "children"),
        Output(ids.DASH_KPIS, "children"),
        Output(ids.DASH_DELAYED, "children"),
        Output(ids.DASH_MS_WARNINGS, "children"),
        Output(ids.DASH_DEP_WARNINGS, "children"),
        Input(ids.DATA_VERSION, "data"),
    )
    def refresh(_version):
        snap = services.snapshot.load()
        data = dashboard_data(snap, Filter(), clock.today(), clock.now())  # all open work
        tasks = {t.id: t for t in snap.tasks}
        today = clock.today()
        return (
            f"All open work · {today:%A, %d %B %Y}",
            kpi_row(data, snap),
            delayed_list(data.delayed, tasks),
            milestone_warning_list(data.milestone_warnings),
            dependency_warning_list(data.dependency_warnings, data.cycles),
        )
