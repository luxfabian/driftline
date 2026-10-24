"""Task detail panel: edit, risk, dependencies, comments, history.

[FUN-02..FUN-07, DAT-04, VAL-06, R-07] (architecture §9.3). The panel is part
of the shell, so later views (e.g. Timeline) can open it too: write the task
id to SELECTED_TASK and set the offcanvas ``is_open``.
"""

from __future__ import annotations

from collections.abc import Sequence

import dash_bootstrap_components as dbc
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update

from pmtool.calc.schedule import dependency_warnings
from pmtool.domain.enums import ChangeKind, CommentKind, TaskStatus
from pmtool.domain.models import ChangeLogEntry, Comment, Task, TaskDetail
from pmtool.errors import NotFound
from pmtool.services import Services
from pmtool.ui import ids
from pmtool.ui.components.task_form import form_fields, register_label_options
from pmtool.ui.feedback import NO_FEEDBACK, run, write_outputs
from pmtool.ui.formatting import (
    FLAG_ARCHIVED,
    FLAG_AT_RISK,
    FLAG_DEPENDENCY,
    FLAG_OVERDUE,
    FLAG_OVERRUN,
    FLAG_STALE,
    fmt_dt,
    milestone_options,
    priority_label,
    task_flags,
    task_options,
)

FORM = ids.EDIT_FORM

STATUS_COLORS = {
    TaskStatus.PLANNED: "secondary",
    TaskStatus.IN_PROGRESS: "primary",
    TaskStatus.BLOCKED: "danger",
    TaskStatus.DONE: "success",
}
FLAG_COLORS = {
    FLAG_ARCHIVED: "dark",
    FLAG_AT_RISK: "warning",
    FLAG_OVERDUE: "danger",
    FLAG_DEPENDENCY: "warning",
    FLAG_STALE: "secondary",
    FLAG_OVERRUN: "info",
}
COMMENT_KINDS = {
    CommentKind.NOTE: "Note",
    CommentKind.RISK_SET: "At risk",
    CommentKind.RISK_CLEARED: "Risk cleared",
    CommentKind.BLOCKED: "Blocked",
    CommentKind.SYSTEM: "System",
}
CHANGE_KINDS = {
    ChangeKind.CREATE: "Created",
    ChangeKind.EDIT: "Edited",
    ChangeKind.REBASELINE: "Re-baselined",
    ChangeKind.ARCHIVE: "Archived",
    ChangeKind.RESTORE: "Restored",
}
FIELD_LABELS = {
    "baseline_start": "Baseline start",
    "baseline_end": "Baseline end",
    "forecast_start": "Forecast start",
    "forecast_end": "Forecast end",
    "remaining_effort_h": "Remaining effort (h)",
    "status": "Status",
}


def _log_value(entry: ChangeLogEntry, value: str | None) -> str:
    if value and entry.field == "status" and value in set(TaskStatus):
        return TaskStatus(value).label
    return value or ""


# --- layout ------------------------------------------------------------------------


def layout() -> dbc.Offcanvas:
    details = html.Div(
        [
            form_fields(FORM, edit=True),
            html.Div(
                [
                    dbc.Button("Save", id=ids.DETAIL_SAVE, color="primary"),
                    dbc.Button(
                        "Mark reviewed", id=ids.DETAIL_REVIEWED, color="secondary", outline=True
                    ),
                    dbc.Button(
                        "Archive",
                        id=ids.DETAIL_ARCHIVE,
                        color="danger",
                        outline=True,
                        className="ms-auto",
                    ),
                ],  # fmt: skip
                className="d-flex gap-2 mt-3",
            ),
            html.Hr(),
            html.H6("At risk"),
            html.Div(id=ids.DETAIL_RISK_TEXT, className="small mb-2"),
            dbc.InputGroup(
                [
                    dbc.Input(id=ids.DETAIL_RISK_REASON, type="text", placeholder="Reason"),
                    dbc.Button("Flag at risk", id=ids.DETAIL_RISK_BUTTON, color="warning"),
                ],
                size="sm",
            ),
        ],
        className="pt-3",
    )
    dependencies = html.Div(
        [
            dbc.Label("Predecessors", className="small mb-1"),
            dcc.Dropdown(id=FORM.predecessors, multi=True, placeholder="None"),
            dbc.Button(
                "Save dependencies",
                id=ids.DETAIL_DEPS_SAVE,
                size="sm",
                color="primary",
                className="mt-2",
            ),  # fmt: skip
            html.P(
                "Dependencies are information only; dates are never changed automatically.",
                className="text-muted small mt-2",
            ),
            html.H6("Successors", className="mt-3"),
            html.Div(id=ids.DETAIL_SUCCESSORS, className="small"),
        ],
        className="pt-3",
    )
    comments = html.Div(
        [
            dbc.Textarea(id=ids.DETAIL_COMMENT_TEXT, rows=2, placeholder="Add a comment"),
            dbc.Button(
                "Add comment",
                id=ids.DETAIL_COMMENT_ADD,
                size="sm",
                color="primary",
                className="mt-2 mb-3",
            ),  # fmt: skip
            html.Div(id=ids.DETAIL_COMMENTS),
        ],
        className="pt-3",
    )
    history = html.Div(id=ids.DETAIL_HISTORY, className="pt-3")
    return dbc.Offcanvas(
        [
            html.Div(id=ids.DETAIL_BADGES, className="d-flex flex-wrap gap-1 mb-2"),
            html.Div(id=ids.DETAIL_WARNINGS),
            dbc.Tabs(
                [
                    dbc.Tab(details, label="Details"),
                    dbc.Tab(dependencies, label="Dependencies"),
                    dbc.Tab(comments, label="Comments"),
                    dbc.Tab(history, label="History"),
                ]
            ),
        ],
        id=ids.DETAIL,
        title="Task",
        is_open=False,
        placement="end",
        scrollable=True,
        style={"width": "min(640px, 100vw)"},
    )


# --- rendering helpers (pure, tested) ---------------------------------------------------


def badges(task: Task, flags: Sequence[str]) -> list:
    items = [
        dbc.Badge(task.status.label, color=STATUS_COLORS[task.status]),
        dbc.Badge(f"Priority {priority_label(task.priority)}", color="light", text_color="dark"),
    ]
    items += [dbc.Badge(f, color=FLAG_COLORS.get(f, "secondary")) for f in flags]
    return items


def warnings(detail: TaskDetail, late_predecessors: Sequence[int]) -> list:
    alerts = []
    if detail.task.is_archived:
        alerts.append(dbc.Alert("This task is archived. Restore it to edit it.", color="dark"))
    if late_predecessors:
        names = {p.id: p.title for p in detail.predecessors}
        items = ", ".join(f"#{i} {names.get(i, '')}".strip() for i in late_predecessors)
        alerts.append(dbc.Alert(f"Starts before these predecessors end: {items}", color="warning"))
    if detail.task.at_risk and detail.risk_reason:
        alerts.append(dbc.Alert(f"At risk: {detail.risk_reason}", color="warning"))
    return [html.Div(a, className="small") for a in alerts]


def comment_list(comments: Sequence[Comment]) -> list:
    if not comments:
        return [html.P("No comments yet.", className="text-muted small")]
    return [
        html.Div(
            [
                html.Div(
                    f"{fmt_dt(c.created_at)} · {COMMENT_KINDS.get(c.kind, c.kind)}",
                    className="text-muted small",
                ),
                html.Div(c.text, style={"whiteSpace": "pre-wrap"}),
            ],  # fmt: skip
            className="border-bottom py-2",
        )
        for c in comments  # newest first (FUN-03)
    ]


def history_table(history: Sequence[ChangeLogEntry]) -> list:
    if not history:
        return [html.P("No history.", className="text-muted small")]
    rows = [
        html.Tr(
            [
                html.Td(fmt_dt(e.changed_at), className="text-nowrap"),
                html.Td(CHANGE_KINDS.get(e.change_kind, e.change_kind)),
                html.Td(FIELD_LABELS.get(e.field, e.field or "")),
                html.Td(_log_value(e, e.old_value)),
                html.Td(_log_value(e, e.new_value)),
                html.Td(e.reason or ""),
            ]
        )
        for e in reversed(history)  # newest first
    ]
    head = html.Thead(
        html.Tr([html.Th(h) for h in ("When", "Change", "Field", "Old", "New", "Reason")])
    )
    return [dbc.Table([head, html.Tbody(rows)], size="sm", striped=True, className="small")]


def successor_list(successors: Sequence[Task]) -> list:
    if not successors:
        return [html.P("No task depends on this one.", className="text-muted")]
    return [html.Ul([html.Li(f"#{t.id} {t.title}") for t in successors])]


# --- callbacks ---------------------------------------------------------------------


def register_callbacks(app: Dash, services: Services) -> None:
    register_label_options(app, FORM)

    @app.callback(
        Output(ids.SELECTED_TASK, "data", allow_duplicate=True),
        Output(ids.DETAIL, "is_open", allow_duplicate=True),
        Input({"type": ids.OPEN_TASK, "index": ALL, "key": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_from_link(_clicks):
        """Any ``ids.open_task`` link opens the panel; new links (n_clicks None) do not."""
        if not ctx.triggered or not ctx.triggered[0]["value"] or not ctx.triggered_id:
            return no_update, no_update
        return ctx.triggered_id["index"], True

    @app.callback(
        Output(FORM.milestone, "options"),
        Output(FORM.predecessors, "options"),
        Input(ids.LOOKUPS, "data"),
        Input(ids.SELECTED_TASK, "data"),
    )
    def lookups(lookup, task_id):
        return milestone_options(lookup), task_options(lookup, exclude=task_id)

    refresh_outputs = {
            "title": Output(ids.DETAIL, "title"),
            "badges": Output(ids.DETAIL_BADGES, "children"),
            "warnings": Output(ids.DETAIL_WARNINGS, "children"),
            "f_title": Output(FORM.title, "value"),
            "f_description": Output(FORM.description, "value"),
            "f_start": Output(FORM.start, "value"),
            "f_end": Output(FORM.end, "value"),
            "f_estimated": Output(FORM.estimated, "value"),
            "f_remaining": Output(FORM.remaining, "value"),
            "f_status": Output(FORM.status, "value"),
            "f_status_reason": Output(FORM.status_reason, "value"),
            "f_priority": Output(FORM.priority, "value"),
            "f_labels": Output(FORM.labels, "value"),
            "f_milestone": Output(FORM.milestone, "value"),
            "f_reason": Output(FORM.reason, "value"),
            "f_predecessors": Output(FORM.predecessors, "value"),
            "successors": Output(ids.DETAIL_SUCCESSORS, "children"),
            "comments": Output(ids.DETAIL_COMMENTS, "children"),
            "comment_text": Output(ids.DETAIL_COMMENT_TEXT, "value"),
            "history": Output(ids.DETAIL_HISTORY, "children"),
            "risk_text": Output(ids.DETAIL_RISK_TEXT, "children"),
            "risk_reason": Output(ids.DETAIL_RISK_REASON, "value"),
            "risk_button": Output(ids.DETAIL_RISK_BUTTON, "children"),
            "archive_button": Output(ids.DETAIL_ARCHIVE, "children"),
            "save_disabled": Output(ids.DETAIL_SAVE, "disabled"),
            "state": Output(ids.DETAIL_STATE, "data"),
    }  # fmt: skip
    unchanged = dict.fromkeys(refresh_outputs, no_update)

    @app.callback(
        output=refresh_outputs,
        inputs={
            "task_id": Input(ids.SELECTED_TASK, "data"),
            "_version": Input(ids.DATA_VERSION, "data"),
        },
    )
    def refresh(task_id, _version):
        if task_id is None:
            return unchanged
        try:
            detail = services.tasks.detail(int(task_id))
        except NotFound:
            return {**unchanged, "title": "Task not found", "state": None}
        snap = services.snapshot.load()
        clock = services.tasks.clock
        late = dependency_warnings(snap.tasks)
        t = detail.task
        flags = task_flags(t, clock.today(), clock.now(), snap.settings.stale_after_days, late)
        return {
            "title": f"Task #{t.id}: {t.title}",
            "badges": badges(t, flags),
            "warnings": warnings(detail, late.get(t.id, [])),
            "f_title": t.title,
            "f_description": t.description or "",
            "f_start": t.forecast_start.isoformat(),
            "f_end": t.forecast_end.isoformat(),
            "f_estimated": t.estimated_effort_h,
            "f_remaining": t.remaining_effort_h,
            "f_status": t.status.value,
            "f_status_reason": "",
            "f_priority": str(int(t.priority)),
            "f_labels": [lb.name for lb in detail.labels],
            "f_milestone": t.milestone_id,
            "f_reason": "",
            "f_predecessors": sorted(t.predecessor_ids),
            "successors": successor_list(detail.successors),
            "comments": comment_list(detail.comments),
            "comment_text": "",
            "history": history_table(detail.history),
            "risk_text": (
                f"Flagged: {detail.risk_reason}" if t.at_risk else "Not flagged."
            ),  # fmt: skip
            "risk_reason": "",
            "risk_button": "Clear risk" if t.at_risk else "Flag at risk",
            "archive_button": "Restore" if t.is_archived else "Archive",
            "save_disabled": t.is_archived,
            "state": {"task_id": t.id, "at_risk": t.at_risk, "archived": t.is_archived},
        }

    @app.callback(
        *write_outputs(),
        Input(ids.DETAIL_SAVE, "n_clicks"),
        Input(ids.DETAIL_REVIEWED, "n_clicks"),
        Input(ids.DETAIL_ARCHIVE, "n_clicks"),
        Input(ids.DETAIL_RISK_BUTTON, "n_clicks"),
        Input(ids.DETAIL_DEPS_SAVE, "n_clicks"),
        Input(ids.DETAIL_COMMENT_ADD, "n_clicks"),
        State(ids.DETAIL_STATE, "data"),
        State(FORM.title, "value"),
        State(FORM.description, "value"),
        State(FORM.start, "value"),
        State(FORM.end, "value"),
        State(FORM.estimated, "value"),
        State(FORM.remaining, "value"),
        State(FORM.status, "value"),
        State(FORM.status_reason, "value"),
        State(FORM.priority, "value"),
        State(FORM.labels, "value"),
        State(FORM.milestone, "value"),
        State(FORM.reason, "value"),
        State(FORM.predecessors, "value"),
        State(ids.DETAIL_RISK_REASON, "value"),
        State(ids.DETAIL_COMMENT_TEXT, "value"),
        State(ids.DATA_VERSION, "data"),
        prevent_initial_call=True,
    )
    def act(_save, _reviewed, _archive, _risk, _deps, _comment, state, title, description,
            start, end, estimated, remaining, status, status_reason, priority, labels,
            milestone, reason, predecessors, risk_reason, comment_text, version):  # fmt: skip
        if not state or not ctx.triggered or not ctx.triggered[0]["value"]:
            return NO_FEEDBACK
        task_id = state["task_id"]
        trigger = ctx.triggered_id
        if trigger == ids.DETAIL_SAVE:
            action = {
                "kind": "save_task",
                "task_id": task_id,
                "title": title,
                "description": description,
                "forecast_start": start,
                "forecast_end": end,
                "estimated_effort_h": estimated,
                "remaining_effort_h": remaining,
                "status": status,
                "status_reason": status_reason,
                "priority": priority,
                "labels": labels or [],
                "milestone_id": milestone,
                "reason": reason,
            }
        elif trigger == ids.DETAIL_REVIEWED:
            action = {"kind": "mark_reviewed", "task_ids": [task_id]}
        elif trigger == ids.DETAIL_ARCHIVE:
            kind = "restore_tasks" if state["archived"] else "archive_tasks"
            action = {"kind": kind, "task_ids": [task_id]}
        elif trigger == ids.DETAIL_RISK_BUTTON:
            action = {"kind": "set_risk", "task_id": task_id, "at_risk": not state["at_risk"],
                      "reason": risk_reason}  # fmt: skip
        elif trigger == ids.DETAIL_DEPS_SAVE:
            action = {"kind": "set_predecessors", "task_id": task_id,
                      "predecessor_ids": predecessors or []}  # fmt: skip
        elif trigger == ids.DETAIL_COMMENT_ADD:
            action = {"kind": "add_comment", "task_id": task_id, "text": comment_text}
        else:
            return NO_FEEDBACK
        _, values = run(services, action, version)
        return values
