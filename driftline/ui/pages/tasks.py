"""Tasks page: filtered, sortable task grid with bulk actions.

[FUN-01, FUN-04, FUN-08, FUN-12, SCH-03] (architecture §9.3).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, State, ctx, html, no_update

from driftline.calc.schedule import dependency_warnings, task_variance
from driftline.domain.filters import Filter, apply_filter
from driftline.domain.models import Snapshot
from driftline.services import Services
from driftline.ui import ids
from driftline.ui.components import filter_bar
from driftline.ui.feedback import NO_FEEDBACK, run, write_outputs
from driftline.ui.formatting import (
    AT_RISK_MARK,
    FLAG_OVERDUE,
    filter_text,
    priority_label,
    task_flags,
)
from driftline.ui.layout import page_header
from driftline.ui.state import filter_from_store
from driftline.ui.theme import CRITICAL, MUTED, WARNING

TINT_CRITICAL, TINT_WARNING = "#f5e4de", "#fbeedd"

PATH = "/tasks"
NAME = "Tasks"
SELECTION_COLUMN = "ag-Grid-SelectionColumn"  # AG Grid's generated checkbox column

COLUMNS: list[dict[str, Any]] = [
    {"field": "id", "headerName": "ID", "width": 80, "filter": "agNumberColumnFilter"},
    {"field": "title", "headerName": "Title", "flex": 3, "minWidth": 220},
    {"field": "status", "headerName": "Status", "width": 120},
    {"field": "priority", "headerName": "Priority", "width": 120},
    {"field": "labels", "headerName": "Labels", "flex": 1, "minWidth": 120},
    {"field": "start", "headerName": "Start", "width": 120},
    {"field": "end", "headerName": "End", "width": 120},
    {"field": "start_variance_d", "headerName": "Start var. (d)", "width": 125,
     "filter": "agNumberColumnFilter",
     "headerTooltip": "Forecast start − baseline start; + = late"},
    {"field": "end_variance_d", "headerName": "End var. (d)", "width": 120,
     "filter": "agNumberColumnFilter", "headerTooltip": "Forecast end − baseline end; + = late"},
    {"field": "remaining_h", "headerName": "Remaining h", "width": 130,
     "filter": "agNumberColumnFilter"},
    {"field": "flags", "headerName": "Flags", "flex": 2, "minWidth": 180},
]  # fmt: skip

ROW_STYLE = {
    "styleConditions": [
        {"condition": "params.data.archived", "style": {"color": MUTED, "fontStyle": "italic"}},
        {
            "condition": "params.data.overdue",
            "style": {"backgroundColor": TINT_CRITICAL, "boxShadow": f"inset 3px 0 0 {CRITICAL}"},
        },
        {
            "condition": "params.data.at_risk",
            "style": {"backgroundColor": TINT_WARNING, "boxShadow": f"inset 3px 0 0 {WARNING}"},
        },
    ]
}


def task_rows(snap: Snapshot, f: Filter, today: date, now: datetime) -> list[dict[str, Any]]:
    """Grid rows for the filtered tasks (pure; tested without Dash)."""
    labels = {lb.id: lb.name for lb in snap.labels}
    late = dependency_warnings(snap.tasks)  # all active tasks, not just the filtered ones
    rows = []
    for t in apply_filter(snap.tasks, f):
        flags = task_flags(t, today, now, snap.settings.stale_after_days, late)
        rows.append(
            {
                "id": t.id,
                "rid": str(t.id),
                "title": f"{AT_RISK_MARK} {t.title}" if t.at_risk else t.title,
                "status": t.status.label,
                "priority": priority_label(t.priority),
                "labels": ", ".join(sorted((labels.get(i, "?") for i in t.label_ids),
                                           key=str.lower)),
                "start": t.forecast_start.isoformat(),
                "end": t.forecast_end.isoformat(),
                "start_variance_d": task_variance(t).start_d,
                "end_variance_d": task_variance(t).end_d,
                "remaining_h": t.remaining_effort_h,
                "flags": " · ".join(flags),
                "overdue": FLAG_OVERDUE in flags,
                "at_risk": t.at_risk,
                "archived": t.is_archived,
            }
        )  # fmt: skip
    return rows


# --- layout ------------------------------------------------------------------------


def layout(**_kwargs) -> html.Div:
    def bulk(label, component_id, color="secondary"):
        return dbc.Button(label, id=component_id, size="sm", color=color, outline=True,
                          disabled=True)  # fmt: skip

    header = page_header(
        NAME,
        ids.TASKS_FILTER_TEXT,
        [
            html.Span(id=ids.TASKS_COUNT, className="pm-hint me-1"),
            bulk("Mark reviewed", ids.BULK_REVIEWED),
            bulk("Re-baseline…", ids.BULK_REBASELINE),
            bulk("Archive", ids.BULK_ARCHIVE, "danger"),
        ],
    )
    grid = dag.AgGrid(
        id=ids.TASK_GRID,
        columnDefs=COLUMNS,
        rowData=[],
        getRowId="params.data.rid",
        getRowStyle=ROW_STYLE,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={
            "rowSelection": {"mode": "multiRow", "enableClickSelection": False},
            "animateRows": False,
            "tooltipShowDelay": 300,
            "localeText": {"noRowsToShow": "No tasks match the filter."},
        },
        style={"height": "calc(100vh - 250px)", "minHeight": "420px"},
        className="ag-theme-alpine",
    )
    rebaseline = dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Re-baseline selected tasks")),
            dbc.ModalBody(
                [
                    html.P(
                        "The current forecast dates become the new baseline. "
                        "Earlier baselines stay in the history.",
                        className="small",
                    ),
                    dbc.Label("Reason (required)", className="small"),
                    dbc.Textarea(id=ids.REBASELINE_REASON, rows=2),
                ]  # fmt: skip
            ),
            dbc.ModalFooter(
                [
                    dbc.Button("Cancel", id=ids.REBASELINE_CANCEL, color="secondary", outline=True),
                    dbc.Button("Re-baseline", id=ids.REBASELINE_OK, color="primary"),
                ]  # fmt: skip
            ),
        ],
        id=ids.REBASELINE_MODAL,
        is_open=False,
    )
    return html.Div([header, filter_bar.layout("tasks"), grid, rebaseline])


# --- callbacks ---------------------------------------------------------------------


def register_callbacks(app: Dash, services: Services) -> None:
    clock = services.tasks.clock

    @app.callback(
        Output(ids.TASK_GRID, "rowData"),
        Output(ids.TASKS_FILTER_TEXT, "children"),
        Output(ids.TASKS_COUNT, "children"),
        Input(ids.DATA_VERSION, "data"),
        Input(ids.FILTER, "data"),
    )
    def refresh(_version, filter_data):
        f = filter_from_store(filter_data)
        snap = services.snapshot.load(include_archived=f.include_archived)
        rows = task_rows(snap, f, clock.today(), clock.now())
        count = f"{len(rows)} task" + ("" if len(rows) == 1 else "s")
        return rows, f"Filter: {filter_text(snap, f)}", count

    @app.callback(
        Output(ids.SELECTED_TASK, "data"),
        Output(ids.DETAIL, "is_open"),
        Input(ids.TASK_GRID, "cellClicked"),
        prevent_initial_call=True,
    )
    def open_detail(cell):
        if not cell or cell.get("colId") == SELECTION_COLUMN or cell.get("rowId") is None:
            return no_update, no_update
        return int(cell["rowId"]), True

    @app.callback(
        Output(ids.BULK_REVIEWED, "disabled"),
        Output(ids.BULK_REBASELINE, "disabled"),
        Output(ids.BULK_ARCHIVE, "disabled"),
        Input(ids.TASK_GRID, "selectedRows"),
    )
    def bulk_enabled(selected):
        disabled = not selected
        return disabled, disabled, disabled

    @app.callback(
        *write_outputs(),
        Input(ids.BULK_REVIEWED, "n_clicks"),
        Input(ids.BULK_ARCHIVE, "n_clicks"),
        State(ids.TASK_GRID, "selectedRows"),
        State(ids.DATA_VERSION, "data"),
        prevent_initial_call=True,
    )
    def bulk(_reviewed, _archive, selected, version):
        if not ctx.triggered or not ctx.triggered[0]["value"]:
            return NO_FEEDBACK
        kind = "mark_reviewed" if ctx.triggered_id == ids.BULK_REVIEWED else "archive_tasks"
        _, values = run(services, {"kind": kind, "task_ids": _ids(selected)}, version)
        return values

    @app.callback(
        Output(ids.REBASELINE_MODAL, "is_open"),
        Output(ids.REBASELINE_REASON, "value"),
        Input(ids.BULK_REBASELINE, "n_clicks"),
        Input(ids.REBASELINE_CANCEL, "n_clicks"),
        prevent_initial_call=True,
    )
    def rebaseline_dialog(_open, _cancel):
        if ctx.triggered_id == ids.REBASELINE_CANCEL:
            return False, no_update
        return True, ""

    @app.callback(
        *write_outputs(),
        Output(ids.REBASELINE_MODAL, "is_open", allow_duplicate=True),
        Input(ids.REBASELINE_OK, "n_clicks"),
        State(ids.REBASELINE_REASON, "value"),
        State(ids.TASK_GRID, "selectedRows"),
        State(ids.DATA_VERSION, "data"),
        prevent_initial_call=True,
    )
    def rebaseline(n, reason, selected, version):
        if not n:
            return (*NO_FEEDBACK, no_update)
        action = {"kind": "rebaseline_tasks", "task_ids": _ids(selected), "reason": reason}
        outcome, values = run(services, action, version)
        return (*values, False if outcome.ok else no_update)


def _ids(selected: list[dict] | None) -> list[int]:
    return [int(row["id"]) for row in selected or []]
