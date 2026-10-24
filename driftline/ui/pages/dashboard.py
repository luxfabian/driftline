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

from driftline.calc.calendar import CalendarContext
from driftline.calc.schedule import (
    DelayItem,
    dependency_cycles,
    dependency_warnings,
    milestone_task_warnings,
    top_delayed,
)
from driftline.calc.status import is_open, is_overdue, is_stale
from driftline.calc.workload import DayPlan, day_plan, load_level, load_ratio
from driftline.domain.enums import Priority, TaskStatus
from driftline.domain.filters import Filter, apply_filter
from driftline.domain.models import Milestone, Snapshot, Task
from driftline.services import Services
from driftline.ui import charts, ids
from driftline.ui.components.kpi import load_tile, stat_tile
from driftline.ui.formatting import AT_RISK_MARK
from driftline.ui.layout import page_header

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
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(id=ids.DASH_DAY_TITLE, className="fw-semibold"),
                                dbc.CardBody(id=ids.DASH_DAY),
                            ],
                            className="mb-3",
                        ),
                        lg=7,
                    ),
                    dbc.Col(
                        [
                            _card("Milestone warnings", ids.DASH_MS_WARNINGS),
                            _card("Dependency warnings", ids.DASH_DEP_WARNINGS),
                        ],
                        lg=5,
                    ),
                ],
                className="g-3",
            ),
            _card("Most delayed", ids.DASH_DELAYED),
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
        stat_tile(
            "Overdue",
            str(data.overdue),
            "forecast end before today",
            charts.STATUS_CRITICAL if data.overdue else None,
        ),
        stat_tile(
            "At risk",
            str(data.at_risk),
            "⚠ flagged tasks",
            charts.STATUS_WARNING if data.at_risk else None,
        ),
        stat_tile(
            "Blocked",
            str(data.blocked),
            "cannot proceed",
            charts.STATUS_CRITICAL if data.blocked else None,
        ),
        stat_tile(
            "Stale",
            str(data.stale),
            f"not reviewed for {s.stale_after_days}+ days",
            charts.STATUS_WARNING if data.stale else None,
        ),
    ]
    return dbc.Row([dbc.Col(t, xs=12, sm=6, xl=True) for t in tiles], className="g-3")


def task_link(t: Task, key: str, today: date, text: str | None = None) -> dbc.Button:
    """Opens the task. At-risk tasks carry ⚠ (FUN-04), overdue ones are brick red (FUN-12)."""
    label = text or f"#{t.id} {t.title}"
    if t.at_risk:
        label = f"{AT_RISK_MARK} {label}"
    overdue = is_overdue(t, today)
    return dbc.Button(
        label,
        id=ids.open_task(t.id, key),
        color="link",
        size="sm",
        className="p-0 text-start align-baseline" + (" pm-overdue-link" if overdue else ""),
        title="Overdue" if overdue else None,
    )


def delayed_list(items: list[DelayItem], tasks: dict[int, Task], today: date):
    if not items:
        return html.P("Nothing is behind its baseline.", className="text-muted small mb-0")
    rows = []
    for item in items:
        if item.kind == "task" and item.id in tasks:
            name = task_link(tasks[item.id], f"delayed{item.id}", today)
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
    head = html.Thead(
        html.Tr(
            [
                html.Th("Item"),
                html.Th("Baseline"),
                html.Th("Forecast"),
                html.Th("Variance", className="text-end"),
            ]
        )
    )
    return dbc.Table([head, html.Tbody(rows)], size="sm", className="small mb-0")


def milestone_warning_list(items: list[tuple[Milestone, date]]):
    if not items:
        return html.P(
            "All milestones are later than their open tasks.", className="text-muted small mb-0"
        )
    return html.Ul(
        [
            html.Li(
                f"◆ {m.name}: forecast {m.forecast_date.isoformat()}, but linked open "
                f"tasks end {end.isoformat()} (+{(end - m.forecast_date).days} d)"
            )
            for m, end in items
        ],
        className="small mb-0",
    )


def dependency_warning_list(
    items: list[tuple[Task, list[Task]]], cycles: list[list[Task]], today: date
):
    if not items and not cycles:
        return html.P(
            "No task starts before its predecessors end.", className="text-muted small mb-0"
        )
    entries = [
        html.Li(
            [
                task_link(t, f"dep{i}", today),
                " starts ",
                t.forecast_start.isoformat(),
                ", before ",
                *_join(
                    [task_link(p, f"dep{i}-{j}", today, f"#{p.id}") for j, p in enumerate(preds)]
                ),
                " end",
                "s" if len(preds) == 1 else "",
            ]
        )
        for i, (t, preds) in enumerate(items)
    ]
    entries += [
        html.Li(
            [
                "Dependency loop: ",
                *_join(
                    [task_link(t, f"loop{i}-{j}", today, f"#{t.id}") for j, t in enumerate(cycle)]
                ),
            ]
        )
        for i, cycle in enumerate(cycles)
    ]
    return html.Ul(entries, className="small mb-0")


def _join(parts: list) -> list:
    result: list = []
    for i, part in enumerate(parts):
        if i:
            result.append(", ")
        result.append(part)
    return result


# --- "Your day": what to work on, in which order --------------------------------------


def day_title(plan: DayPlan, today: date) -> str:
    if plan.day is None:
        return "Your day"
    if plan.day == today:
        return f"Your day · {plan.day:%A, %d %B}"
    return f"Your next working day · {plan.day:%A, %d %B}"


def due_text(due: date, overdue: bool, forecast_end: date, today: date) -> str:
    if overdue:
        days = (today - forecast_end).days
        return f"overdue {days} d"
    if due == today:
        return "due today"
    if (due - today).days < 7:
        return f"due {due:%a}"
    return f"due {due:%d %b}"


def priority_bar(plan: DayPlan, tasks: dict[int, Task]) -> html.Div:
    """Workable hours of the day split by priority, with a mark where capacity ends."""
    by_priority = dict.fromkeys(Priority, 0.0)
    for item in plan.items:
        if not item.blocked:
            by_priority[tasks[item.task_id].priority] += item.hours
    scale = max(plan.workable_h, plan.capacity_h, 1e-9)
    segments = [
        html.Div(
            className="pm-daybar-seg",
            title=f"{p.label}: {h:.1f} h",
            style={
                "width": f"{100 * h / scale:.2f}%",
                "background": charts.PRIORITY_COLORS[p.label],
            },
        )
        for p, h in by_priority.items()
        if h > 0
    ]
    marker = html.Div(
        className="pm-daybar-cap",
        title=f"Plannable: {plan.capacity_h:.1f} h",
        style={"left": f"{100 * plan.capacity_h / scale:.2f}%"},
    )
    legend = [
        html.Span(
            [
                html.Span(
                    className="pm-dot", style={"background": charts.PRIORITY_COLORS[p.label]}
                ),
                f"{p.label} {h:.1f} h",
            ],
            className="me-3",
        )
        for p, h in by_priority.items()
        if h > 0
    ]
    return html.Div(
        [
            html.Div([*segments, marker], className="pm-daybar"),
            html.Div(legend, className="pm-hint mt-1"),
        ]
    )


def day_section(
    plan: DayPlan, tasks: dict[int, Task], milestone_names: dict[int, str], today: date
) -> list:
    """Summary, priority bar, focus list with the capacity cut, then blocked work."""
    if plan.day is None:
        return [
            html.P(
                "No working day within the next year (check absences in Settings).",
                className="text-muted mb-0",
            )
        ]
    if not plan.items:
        return [
            html.P(
                "Nothing is planned for this day. A good moment to review the backlog.",
                className="text-muted mb-0",
            )
        ]
    over = plan.workable_h - plan.capacity_h
    if plan.capacity_h <= 0:
        verdict = html.Span("no plannable time", className="pm-verdict pm-verdict-bad")
    elif over > 0.05:
        verdict = html.Span(f"✕ {over:.1f} h more than fits", className="pm-verdict pm-verdict-bad")
    else:
        verdict = html.Span(f"✓ fits, {-over:.1f} h to spare", className="pm-verdict pm-verdict-ok")
    summary = html.Div(
        [
            html.Span(f"{plan.workable_h:.1f} h", className="pm-day-hours"),
            html.Span(f" of work · {plan.capacity_h:.1f} h plannable · ", className="text-muted"),
            verdict,
        ],
        className="mb-2",
    )

    rows, cut_done, rank = [], False, 0
    for item in plan.items:
        if item.blocked:
            continue
        t = tasks[item.task_id]
        if not item.within_capacity and not cut_done:
            rows.append(
                html.Tr(html.Td("plannable time ends here", colSpan=5), className="pm-cutline")
            )
            cut_done = True
        rank += 1
        rows.append(
            html.Tr(
                [
                    html.Td(str(rank), className="text-muted tabular"),
                    html.Td(
                        [
                            task_link(t, f"day{t.id}", today),
                            html.Div(milestone_names.get(t.milestone_id, ""), className="pm-hint"),
                        ]
                    ),
                    html.Td(
                        [
                            html.Span(
                                className="pm-dot",
                                style={"background": charts.PRIORITY_COLORS[t.priority.label]},
                            ),
                            t.priority.label,
                        ]
                    ),
                    html.Td(f"{item.hours:.1f} h", className="text-end tabular"),
                    html.Td(
                        due_text(item.due, item.overdue, t.forecast_end, today),
                        className="pm-due-overdue" if item.overdue else "text-muted",
                    ),
                ],
                className="" if item.within_capacity else "pm-beyond",
            )
        )
    focus = dbc.Table(html.Tbody(rows), size="sm", className="small mb-0 pm-daytable")
    blocked = [i for i in plan.items if i.blocked]
    extra = []
    if blocked:
        extra.append(
            html.Div(
                [
                    html.Span("Blocked, not workable: ", className="text-muted"),
                    *_join(
                        [
                            html.Span(
                                [
                                    task_link(tasks[i.task_id], f"dayb{i.task_id}", today),
                                    f" ({i.hours:.1f} h)",
                                ]
                            )
                            for i in blocked
                        ]
                    ),
                ],
                className="small mt-2",
            )
        )
    hint = html.Div(
        "Order: priority, then due date (at-risk first). Hours follow the workload model: "
        "each task's remaining effort spread over its working days.",
        className="pm-hint mt-2",
    )
    return [summary, priority_bar(plan, tasks), focus, *extra, hint]


# --- callbacks ---------------------------------------------------------------------


def register_callbacks(app: Dash, services: Services) -> None:
    clock = services.tasks.clock

    @app.callback(
        Output(ids.DASH_FILTER_TEXT, "children"),
        Output(ids.DASH_KPIS, "children"),
        Output(ids.DASH_DAY_TITLE, "children"),
        Output(ids.DASH_DAY, "children"),
        Output(ids.DASH_DELAYED, "children"),
        Output(ids.DASH_MS_WARNINGS, "children"),
        Output(ids.DASH_DEP_WARNINGS, "children"),
        Input(ids.DATA_VERSION, "data"),
    )
    def refresh(_version):
        snap = services.snapshot.load()
        today = clock.today()
        data = dashboard_data(snap, Filter(), today, clock.now())  # all open work
        tasks = {t.id: t for t in snap.tasks}
        plan = day_plan(snap.tasks, today, CalendarContext.from_snapshot(snap))
        return (
            f"All open work · {today:%A, %d %B %Y}",
            kpi_row(data, snap),
            day_title(plan, today),
            day_section(plan, tasks, {m.id: m.name for m in snap.milestones}, today),
            delayed_list(data.delayed, tasks, today),
            milestone_warning_list(data.milestone_warnings),
            dependency_warning_list(data.dependency_warnings, data.cycles, today),
        )
