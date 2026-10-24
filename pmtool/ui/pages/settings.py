"""Settings page [WL-01, WL-07, WL-08, NFR-03, NFR-08, DAT-08] (architecture §9.3).

Capacity and thresholds, absences, public holidays, export, CSV import and
archived items (restore / delete permanently, which asks for confirmation).
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import dash_bootstrap_components as dbc
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update

from pmtool.calc.calendar import daily_capacity
from pmtool.domain.models import Absence, Holiday, Milestone, Settings, Task
from pmtool.services import Services
from pmtool.services.import_service import ImportResult
from pmtool.ui import ids
from pmtool.ui.actions import Outcome
from pmtool.ui.feedback import NO_FEEDBACK, feedback, run, write_outputs

PATH = "/settings"
NAME = "Settings"
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
SETTING_FIELDS = (
    ids.SET_WEEKLY_HOURS, ids.SET_WEEKDAYS, ids.SET_PLANNABLE_PCT, ids.SET_HORIZON,
    ids.SET_GREEN_PCT, ids.SET_AMBER_PCT, ids.SET_STALE_DAYS, ids.SET_BACKUP_KEEP, ids.SET_TOP_N,
)  # fmt: skip


# --- pure helpers (tested) ------------------------------------------------------------


def form_values(s: Settings) -> list[Any]:
    """Settings -> form values, in SETTING_FIELDS order (fractions shown as %)."""
    return [
        s.weekly_hours,
        list(s.working_weekdays),
        round(s.plannable_fraction * 100, 2),
        s.default_horizon_weeks,
        round(s.load_green_max * 100, 2),
        round(s.load_amber_max * 100, 2),
        s.stale_after_days,
        s.backup_keep_count,
        s.top_delayed_n,
    ]


def settings_values(hours, weekdays, plannable_pct, horizon, green_pct, amber_pct, stale,
                    backup_keep, top_n) -> dict[str, Any]:  # fmt: skip
    """Form values -> SettingsService.update kwargs. Empty fields stay as they are."""
    values = {
        "weekly_hours": hours,
        "working_weekdays": sorted(int(d) for d in weekdays or []),
        "plannable_fraction": _fraction(plannable_pct),
        "default_horizon_weeks": horizon,
        "load_green_max": _fraction(green_pct),
        "load_amber_max": _fraction(amber_pct),
        "stale_after_days": stale,
        "backup_keep_count": backup_keep,
        "top_delayed_n": top_n,
    }
    return {k: v for k, v in values.items() if v is not None and v != ""}


def _fraction(pct) -> float | None:
    return None if pct is None or pct == "" else float(pct) / 100


def capacity_note(hours, weekdays, plannable_pct) -> str:
    try:
        s = Settings(weekly_hours=float(hours), working_weekdays=tuple(weekdays or ()),
                     plannable_fraction=float(plannable_pct) / 100)  # fmt: skip
    except (TypeError, ValueError):
        return ""
    per_day = daily_capacity(s)
    return (f"= {per_day:.2f} h plannable per working day, "
            f"{per_day * len(s.working_weekdays):.1f} h per full week")  # fmt: skip


def export_name(now: datetime, extension: str) -> str:
    return f"pmtool_export_{now:%Y%m%d_%H%M}.{extension}"


def import_summary(result: ImportResult) -> html.Div:
    if result.ok:
        return dbc.Alert(f"Imported {result.imported} task(s).", color="success",
                         className="small mb-0")  # fmt: skip
    items = [html.Li(f"Line {e.line}: {e.message}") for e in result.errors]
    return dbc.Alert(
        [html.Strong("Nothing was imported. "), "Fix these lines and upload again:",
         html.Ul(items, className="mb-0")],
        color="danger",
        className="small mb-0",
    )  # fmt: skip


# --- layout ------------------------------------------------------------------------


def layout(**_kwargs) -> html.Div:
    capacity = _card(
        "Capacity and thresholds",
        [
            dbc.Row(
                [
                    _num("Weekly working hours", ids.SET_WEEKLY_HOURS, step=0.5),
                    _num("Plannable fraction (%)", ids.SET_PLANNABLE_PCT, step=1),
                ]
            ),
            dbc.Label("Working weekdays", className="small mb-1"),
            dbc.Checklist(id=ids.SET_WEEKDAYS, inline=True,
                          options=[{"label": d, "value": i} for i, d in enumerate(WEEKDAYS, 1)]),
            html.Div(id=ids.SET_DAILY_NOTE, className="text-muted small mb-3"),
            dbc.Row(
                [
                    _num("Default horizon (weeks)", ids.SET_HORIZON, step=1),
                    _num("Load green below (%)", ids.SET_GREEN_PCT, step=1),
                    _num("Load amber up to (%)", ids.SET_AMBER_PCT, step=1),
                ]
            ),
            dbc.Row(
                [
                    _num("Stale after (days)", ids.SET_STALE_DAYS, step=1),
                    _num("Backups to keep", ids.SET_BACKUP_KEEP, step=1),
                    _num("Most delayed: show", ids.SET_TOP_N, step=1),
                ]
            ),
            dbc.Button("Save settings", id=ids.SET_SAVE, color="primary", size="sm"),
        ],
    )  # fmt: skip
    absences = _card(
        "Absences (vacation, sick leave …)",
        [
            dbc.Row(
                [
                    dbc.Col(dbc.Input(id=ids.ABS_START, type="date", size="sm"), md=4),
                    dbc.Col(dbc.Input(id=ids.ABS_END, type="date", size="sm"), md=4),
                    dbc.Col(dbc.Input(id=ids.ABS_NOTE, placeholder="Note", size="sm"), md=4),
                ],
                className="g-2 mb-2",
            ),
            dbc.Button("Add absence", id=ids.ABS_ADD, size="sm", color="secondary",
                       outline=True, className="mb-2"),
            html.Div(id=ids.ABS_LIST),
        ],
    )  # fmt: skip
    holidays = _card(
        "Public holidays",
        [
            dbc.Row(
                [
                    dbc.Col(dbc.Input(id=ids.HOL_DATE, type="date", size="sm"), md=4),
                    dbc.Col(dbc.Input(id=ids.HOL_NAME, placeholder="Name", size="sm"), md=8),
                ],
                className="g-2 mb-2",
            ),
            dbc.Button("Add holiday", id=ids.HOL_ADD, size="sm", color="secondary",
                       outline=True, className="mb-2"),
            html.Div(id=ids.HOL_LIST),
        ],
    )  # fmt: skip
    data = _card(
        "Export and import",
        [
            html.P("Export tasks, milestones, comments and change history.", className="small"),
            html.Div(
                [dbc.Button("Excel (.xlsx)", id=ids.EXPORT_EXCEL, size="sm", color="primary"),
                 dbc.Button("CSV (.zip)", id=ids.EXPORT_CSV, size="sm", color="primary",
                            outline=True)],
                className="d-flex gap-2 mb-3",
            ),
            html.P(
                ["Import tasks from a CSV file (UTF-8, comma-separated). Required columns: ",
                 html.Code("title, forecast_start, forecast_end, estimated_effort_h"),
                 "; optional: ", html.Code("priority, labels, description"),
                 ". Labels are separated by semicolons. An exported tasks.csv works too."],
                className="small",
            ),
            dcc.Upload(
                id=ids.IMPORT_UPLOAD,
                children=html.Div(["Drop a CSV file here or ", html.A("choose one")]),
                accept=".csv,text/csv",
                multiple=False,
                className="border border-2 rounded text-center p-3 small mb-2",
                style={"borderStyle": "dashed"},
            ),
            dbc.Button("Download CSV template", id=ids.IMPORT_TEMPLATE, size="sm",
                       color="link", className="p-0 mb-2"),
            html.Div(id=ids.IMPORT_RESULT),
            dcc.Download(id=ids.EXPORT_DOWNLOAD),
        ],
    )  # fmt: skip
    archive = _card(
        "Archived items",
        [
            html.P("Archived items are hidden everywhere else. Restore them, or delete them "
                   "permanently including their history.", className="small"),
            html.H6("Tasks", className="mt-2"),
            html.Div(id=ids.ARCHIVED_TASKS),
            html.H6("Milestones", className="mt-3"),
            html.Div(id=ids.ARCHIVED_MILESTONES),
        ],
    )  # fmt: skip
    return html.Div(
        [
            html.H4(NAME),
            dbc.Row(
                [dbc.Col([capacity, absences, holidays], lg=6), dbc.Col([data, archive], lg=6)],
                className="g-3",
            ),
        ]
    )


def _card(title: str, body: list) -> dbc.Card:
    return dbc.Card(
        [dbc.CardHeader(title, className="fw-semibold"), dbc.CardBody(body)], className="mb-3"
    )


def _num(label: str, component_id: str, step: float) -> dbc.Col:
    return dbc.Col(
        [
            dbc.Label(label, className="small mb-1"),
            dbc.Input(id=component_id, type="number", step=step, size="sm"),
        ],
        className="mb-2",
    )


def _row_button(label: str, action: str, index, color: str = "secondary") -> dbc.Button:
    return dbc.Button(label, id=ids.row_action(action, index), size="sm", color=color,
                      outline=True, className="py-0")  # fmt: skip


def _table(rows: list, empty: str) -> Any:
    if not rows:
        return html.P(empty, className="text-muted small mb-0")
    return dbc.Table(html.Tbody(rows), size="sm", className="small mb-0 align-middle")


def absence_rows(absences: Sequence[Absence]) -> Any:
    rows = [
        html.Tr([html.Td(f"{a.start_date.isoformat()} – {a.end_date.isoformat()}"),
                 html.Td(a.note or ""),
                 html.Td(_row_button("Remove", "remove_absence", a.id), className="text-end")])
        for a in sorted(absences, key=lambda a: a.start_date)
    ]  # fmt: skip
    return _table(rows, "No absences.")


def holiday_rows(holidays: Sequence[Holiday]) -> Any:
    rows = [
        html.Tr([html.Td(h.date.isoformat()), html.Td(h.name or ""),
                 html.Td(_row_button("Remove", "remove_holiday", h.date.isoformat()),
                         className="text-end")])
        for h in sorted(holidays, key=lambda h: h.date)
    ]  # fmt: skip
    return _table(rows, "No public holidays.")


def archived_rows(items: Sequence[Task | Milestone], kind: str) -> Any:
    rows = []
    for item in items:
        name = item.title if kind == "task" else item.name
        rows.append(
            html.Tr(
                [
                    html.Td(f"#{item.id} {name}"),
                    html.Td(f"archived {item.archived_at:%Y-%m-%d}", className="text-muted"),
                    html.Td(
                        html.Div(
                            [
                                _row_button("Restore", f"restore_{kind}", item.id),
                                _row_button("Delete…", f"delete_{kind}", item.id, "danger"),
                            ],
                            className="d-flex gap-1 justify-content-end",
                        )  # fmt: skip
                    ),
                ]
            )
        )
    return _table(rows, f"No archived {kind}s.")


def row_action_to_action(action: str, index) -> dict[str, Any] | None:
    """Pattern-matching button -> action dict (pure)."""
    match action:
        case "remove_absence":
            return {"kind": "remove_absence", "absence_id": index}
        case "remove_holiday":
            return {"kind": "remove_holiday", "date": index}
        case "restore_task":
            return {"kind": "restore_tasks", "task_ids": [index]}
        case "delete_task":
            return {"kind": "delete_task", "task_id": index}
        case "restore_milestone":
            return {"kind": "restore_milestones", "milestone_ids": [index]}
        case "delete_milestone":
            return {"kind": "delete_milestone", "milestone_id": index}
    return None


# --- callbacks ---------------------------------------------------------------------


def register_callbacks(app: Dash, services: Services) -> None:
    clock = services.tasks.clock

    @app.callback(
        *[Output(f, "value") for f in SETTING_FIELDS],
        Output(ids.ABS_LIST, "children"),
        Output(ids.HOL_LIST, "children"),
        Output(ids.ARCHIVED_TASKS, "children"),
        Output(ids.ARCHIVED_MILESTONES, "children"),
        Input(ids.DATA_VERSION, "data"),
    )
    def refresh(_version):
        snap = services.snapshot.load(include_archived=True)
        holidays = services.settings.list_holidays()
        return (
            *form_values(snap.settings),
            absence_rows(snap.absences),
            holiday_rows(holidays),
            archived_rows([t for t in snap.tasks if t.is_archived], "task"),
            archived_rows([m for m in snap.milestones if m.is_archived], "milestone"),
        )

    @app.callback(
        Output(ids.SET_DAILY_NOTE, "children"),
        Input(ids.SET_WEEKLY_HOURS, "value"),
        Input(ids.SET_WEEKDAYS, "value"),
        Input(ids.SET_PLANNABLE_PCT, "value"),
    )
    def note(hours, weekdays, pct):
        return capacity_note(hours, weekdays, pct)

    @app.callback(
        *write_outputs(),
        Input(ids.SET_SAVE, "n_clicks"),
        *[State(f, "value") for f in SETTING_FIELDS],
        State(ids.DATA_VERSION, "data"),
        prevent_initial_call=True,
    )
    def save(n, *values):
        if not n:
            return NO_FEEDBACK
        *form, version = values
        action = {"kind": "update_settings", "values": settings_values(*form)}
        return run(services, action, version)[1]

    @app.callback(
        *write_outputs(),
        Output(ids.ABS_START, "value"),
        Output(ids.ABS_END, "value"),
        Output(ids.ABS_NOTE, "value"),
        Input(ids.ABS_ADD, "n_clicks"),
        State(ids.ABS_START, "value"),
        State(ids.ABS_END, "value"),
        State(ids.ABS_NOTE, "value"),
        State(ids.DATA_VERSION, "data"),
        prevent_initial_call=True,
    )
    def add_absence(n, start, end, note_text, version):
        if not n:
            return (*NO_FEEDBACK, no_update, no_update, no_update)
        action = {"kind": "add_absence", "start_date": start, "end_date": end, "note": note_text}
        outcome, values = run(services, action, version)
        cleared = ("", "", "") if outcome.ok else (no_update,) * 3
        return (*values, *cleared)

    @app.callback(
        *write_outputs(),
        Output(ids.HOL_DATE, "value"),
        Output(ids.HOL_NAME, "value"),
        Input(ids.HOL_ADD, "n_clicks"),
        State(ids.HOL_DATE, "value"),
        State(ids.HOL_NAME, "value"),
        State(ids.DATA_VERSION, "data"),
        prevent_initial_call=True,
    )
    def add_holiday(n, day, name, version):
        if not n:
            return (*NO_FEEDBACK, no_update, no_update)
        outcome, values = run(services, {"kind": "add_holiday", "date": day, "name": name},
                              version)  # fmt: skip
        return (*values, *(("", "") if outcome.ok else (no_update, no_update)))

    @app.callback(
        *write_outputs(),
        Input({"type": ids.ROW_ACTION, "action": ALL, "index": ALL}, "n_clicks"),
        State(ids.DATA_VERSION, "data"),
        prevent_initial_call=True,
    )
    def row_action(_clicks, version):
        trigger = ctx.triggered_id
        if not trigger or not ctx.triggered or not ctx.triggered[0]["value"]:
            return NO_FEEDBACK  # buttons appearing after a refresh, not a click
        action = row_action_to_action(trigger["action"], trigger["index"])
        if action is None:
            return NO_FEEDBACK
        return run(services, action, version)[1]

    @app.callback(
        Output(ids.EXPORT_DOWNLOAD, "data"),
        Input(ids.EXPORT_EXCEL, "n_clicks"),
        Input(ids.EXPORT_CSV, "n_clicks"),
        Input(ids.IMPORT_TEMPLATE, "n_clicks"),
        prevent_initial_call=True,
    )
    def download(_excel, _csv, _template):
        if not ctx.triggered or not ctx.triggered[0]["value"]:
            return no_update
        now = clock.now()
        if ctx.triggered_id == ids.EXPORT_EXCEL:
            return dcc.send_bytes(services.export.to_excel(), export_name(now, "xlsx"))
        if ctx.triggered_id == ids.EXPORT_CSV:
            return dcc.send_bytes(services.export.to_csv_zip(), export_name(now, "zip"))
        return dcc.send_bytes(services.importer.template_csv(), "pmtool_import_template.csv")

    @app.callback(
        *write_outputs(),
        Output(ids.IMPORT_RESULT, "children"),
        Output(ids.IMPORT_UPLOAD, "contents"),
        Input(ids.IMPORT_UPLOAD, "contents"),
        State(ids.IMPORT_UPLOAD, "filename"),
        State(ids.DATA_VERSION, "data"),
        prevent_initial_call=True,
    )
    def upload(contents, filename, version):
        if not contents:
            return (*NO_FEEDBACK, no_update, no_update)
        try:
            data = base64.b64decode(contents.split(",", 1)[1])
        except (IndexError, ValueError):
            outcome = Outcome("error", f"Could not read {filename or 'the file'}.")
            return (*feedback(outcome, version), no_update, None)
        result = services.importer.from_csv(data)
        if result.ok:
            outcome = Outcome("ok", f"Imported {result.imported} task(s) from {filename}.")
        else:
            outcome = Outcome("error", f"{filename}: nothing imported, see the list of errors.")
        # Clearing contents lets the same file be uploaded again after fixing it.
        return (*feedback(outcome, version), import_summary(result), None)
