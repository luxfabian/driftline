"""Milestones page: table, actions and milestone trend analysis.

[DAT-05, FUN-02, SCH-02..SCH-05] (architecture §9.3).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

from pmtool.calc.schedule import milestone_task_warnings, milestone_variance, mta_series
from pmtool.calc.status import is_open
from pmtool.domain.enums import MilestoneStatus
from pmtool.domain.filters import Filter
from pmtool.domain.models import Milestone, Snapshot
from pmtool.errors import NotFound
from pmtool.services import Services
from pmtool.ui import charts, ids
from pmtool.ui.feedback import NO_FEEDBACK, run, write_outputs
from pmtool.ui.formatting import filter_text
from pmtool.ui.state import filter_from_store

PATH = "/milestones"
NAME = "Milestones"

COLUMNS: list[dict[str, Any]] = [
    {"field": "id", "headerName": "ID", "width": 70},
    {"field": "name", "headerName": "Name", "flex": 2, "minWidth": 160},
    {"field": "status", "headerName": "Status", "width": 105},
    {"field": "baseline", "headerName": "Baseline", "width": 115},
    {"field": "forecast", "headerName": "Forecast", "width": 115},
    {"field": "variance_d", "headerName": "Variance (d)", "width": 115,
     "headerTooltip": "Forecast − baseline; + = late"},
    {"field": "achieved", "headerName": "Achieved", "width": 115},
    {"field": "open_tasks", "headerName": "Open tasks", "width": 110},
    {"field": "warning", "headerName": "Warning", "flex": 2, "minWidth": 160},
]  # fmt: skip
ROW_STYLE = {
    "styleConditions": [
        {"condition": "params.data.archived", "style": {"color": "#6c757d", "fontStyle": "italic"}},
        {"condition": "params.data.warning", "style": {"backgroundColor": "#fff3cd"}},
    ]
}

# Dialog modes -> (title, rows shown, date label)
DIALOG = {
    "create": ("New milestone", {"name", "description", "date"}, "Forecast date"),
    "edit": ("Edit milestone", {"name", "description", "date", "reason"}, "Forecast date"),
    "achieve": ("Mark milestone achieved", {"date"}, "Achieved date"),
    "rebaseline": ("Re-baseline milestones", {"reason"}, ""),
}


def milestone_filter(f: Filter) -> Filter:
    """The part of the task filter that applies to milestones."""
    return Filter(milestone_ids=f.milestone_ids, include_archived=f.include_archived)


def shown_milestones(snap: Snapshot, f: Filter) -> list[Milestone]:
    """Milestone filter applies; other task filters do not. Archived only on request."""
    return sorted(
        (
            m for m in snap.milestones
            if (not f.milestone_ids or m.id in f.milestone_ids)
            and (f.include_archived or not m.is_archived)
        ),
        key=lambda m: (m.forecast_date, m.id),
    )  # fmt: skip


def milestone_rows(snap: Snapshot, f: Filter) -> list[dict[str, Any]]:
    milestones = shown_milestones(snap, f)
    active = [t for t in snap.tasks if not t.is_archived]
    warnings = milestone_task_warnings(milestones, active)  # SCH-05
    open_counts: dict[int, int] = {}
    for t in active:
        if t.milestone_id is not None and is_open(t):
            open_counts[t.milestone_id] = open_counts.get(t.milestone_id, 0) + 1
    rows = []
    for m in milestones:
        warning = ""
        if m.id in warnings:
            end = warnings[m.id]
            warning = f"Linked tasks end {end.isoformat()} (+{(end - m.forecast_date).days} d)"
        rows.append(
            {
                "id": m.id,
                "rid": str(m.id),
                "name": m.name,
                "status": m.status.label + (" (archived)" if m.is_archived else ""),
                "baseline": m.baseline_date.isoformat(),
                "forecast": m.forecast_date.isoformat(),
                "variance_d": milestone_variance(m),
                "achieved": m.achieved_date.isoformat() if m.achieved_date else "",
                "open_tasks": open_counts.get(m.id, 0),
                "warning": warning,
                "achieved_flag": m.status is MilestoneStatus.ACHIEVED,
                "archived": m.is_archived,
            }
        )
    return rows


def mta_figure(snap: Snapshot, f: Filter, today: date, selected: Sequence[int] | None) -> go.Figure:
    """SCH-04 from the change log; achieved milestones end on their achieved date."""
    milestones = shown_milestones(snap, f)
    if selected:
        milestones = [m for m in milestones if m.id in set(selected)]
    by_id = charts.categorical_colors(sorted(m.id for m in snap.milestones))
    series: dict[str, list[tuple[date, date]]] = {}
    colors: dict[str, str] = {}
    for m in milestones:
        name = m.name if m.name not in series else f"{m.name} (#{m.id})"
        series[name] = mta_series(
            snap.milestone_forecast_log.get(m.id, ()), today, until=m.achieved_date
        )
        colors[name] = by_id.get(m.id, charts.OTHER_COLOR)
    return charts.build_mta(series, today, filter_text(snap, milestone_filter(f)), colors=colors)


# --- layout ------------------------------------------------------------------------


def layout(**_kwargs) -> html.Div:
    def button(label, component_id, color="secondary", outline=True, disabled=True):
        return dbc.Button(label, id=component_id, size="sm", color=color, outline=outline,
                          disabled=disabled)  # fmt: skip

    toolbar = html.Div(
        [
            html.Div([html.H4(NAME, className="mb-0"),
                      html.Div(id=ids.MS_FILTER_TEXT, className="text-muted small")]),
            html.Div(
                [
                    button("+ New milestone", ids.MS_NEW, "primary", False, False),
                    button("Edit…", ids.MS_EDIT),
                    button("Achieved…", ids.MS_ACHIEVE),
                    button("Reopen", ids.MS_REOPEN),
                    button("Re-baseline…", ids.MS_REBASELINE),
                    button("Archive", ids.MS_ARCHIVE, "danger"),
                ],
                className="d-flex gap-2 flex-wrap",
            ),
        ],
        className="d-flex justify-content-between align-items-end flex-wrap gap-2 mb-2",
    )  # fmt: skip
    grid = dag.AgGrid(
        id=ids.MS_GRID,
        columnDefs=COLUMNS,
        rowData=[],
        getRowId="params.data.rid",
        getRowStyle=ROW_STYLE,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={
            "rowSelection": {"mode": "multiRow", "enableClickSelection": True},
            "localeText": {"noRowsToShow": "No milestones yet."},
            "domLayout": "autoHeight",
        },
        className="ag-theme-alpine mb-3",
    )
    mta = html.Div(
        [
            dbc.Label("Milestones in the trend chart", className="small mb-1"),
            dcc.Dropdown(id=ids.MTA_SELECT, multi=True, placeholder="All shown milestones",
                         persistence=True, persistence_type="session"),
            dcc.Graph(id=ids.MTA_GRAPH, config={"displaylogo": False}),
            html.P(
                "Each line shows how the forecast date moved over time. Rising lines slip; "
                "a line that reaches the diagonal was achieved (or is due) on that day.",
                className="text-muted small",
            ),
        ]
    )  # fmt: skip
    return html.Div([toolbar, grid, mta, _dialog(), dcc.Store(id=ids.MS_DIALOG_MODE)])


def _dialog() -> dbc.Modal:
    def row(row_id, label, control, label_id=None):
        extra = {"id": label_id} if label_id else {}
        return html.Div([dbc.Label(label, className="small mb-1", **extra), control],
                        id=row_id, className="mb-2")  # fmt: skip

    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle(id=ids.MS_DIALOG_TITLE)),
            dbc.ModalBody(
                [
                    row(ids.MS_ROW_NAME, "Name", dbc.Input(id=ids.MS_NAME, type="text")),
                    row(
                        ids.MS_ROW_DESCRIPTION,
                        "Description",
                        dbc.Textarea(id=ids.MS_DESCRIPTION, rows=2),
                    ),
                    row(
                        ids.MS_ROW_DATE,
                        "Date",
                        dbc.Input(id=ids.MS_DATE, type="date"),
                        label_id=ids.MS_DATE_LABEL,
                    ),
                    row(ids.MS_ROW_REASON, "Reason", dbc.Input(id=ids.MS_REASON, type="text")),
                ]  # fmt: skip
            ),
            dbc.ModalFooter(
                [
                    dbc.Button("Cancel", id=ids.MS_CANCEL, color="secondary", outline=True),
                    dbc.Button("Save", id=ids.MS_SAVE, color="primary"),
                ]
            ),
        ],
        id=ids.MS_DIALOG,
        is_open=False,
    )


# --- callbacks ---------------------------------------------------------------------


def register_callbacks(app: Dash, services: Services) -> None:
    clock = services.tasks.clock

    @app.callback(
        Output(ids.MS_GRID, "rowData"),
        Output(ids.MS_FILTER_TEXT, "children"),
        Output(ids.MTA_SELECT, "options"),
        Output(ids.MTA_GRAPH, "figure"),
        Input(ids.DATA_VERSION, "data"),
        Input(ids.FILTER, "data"),
        Input(ids.MTA_SELECT, "value"),
    )
    def refresh(_version, filter_data, selected):
        f = filter_from_store(filter_data)
        snap = services.snapshot.load(include_archived=True)
        rows = milestone_rows(snap, f)
        options = [{"label": r["name"], "value": r["id"]} for r in rows]
        text = f"Filter: {filter_text(snap, milestone_filter(f))}"
        return rows, text, options, mta_figure(snap, f, clock.today(), selected)

    @app.callback(
        Output(ids.MS_EDIT, "disabled"),
        Output(ids.MS_ACHIEVE, "disabled"),
        Output(ids.MS_REOPEN, "disabled"),
        Output(ids.MS_REBASELINE, "disabled"),
        Output(ids.MS_ARCHIVE, "disabled"),
        Output(ids.MS_ARCHIVE, "children"),
        Input(ids.MS_GRID, "selectedRows"),
    )
    def buttons(selected):
        rows = selected or []
        one = rows[0] if len(rows) == 1 else None
        active_one = one is not None and not one["archived"]
        any_archived = any(r["archived"] for r in rows)
        all_archived = bool(rows) and all(r["archived"] for r in rows)
        return (
            not active_one,
            not (active_one and not one["achieved_flag"]),
            not (active_one and one["achieved_flag"]),
            not rows or any_archived,
            not rows or (any_archived and not all_archived),
            "Restore" if all_archived else "Archive",
        )

    @app.callback(
        Output(ids.MS_DIALOG, "is_open"),
        Output(ids.MS_DIALOG_TITLE, "children"),
        Output(ids.MS_DIALOG_MODE, "data"),
        Output(ids.MS_ROW_NAME, "hidden"),
        Output(ids.MS_ROW_DESCRIPTION, "hidden"),
        Output(ids.MS_ROW_DATE, "hidden"),
        Output(ids.MS_ROW_REASON, "hidden"),
        Output(ids.MS_DATE_LABEL, "children"),
        Output(ids.MS_NAME, "value"),
        Output(ids.MS_DESCRIPTION, "value"),
        Output(ids.MS_DATE, "value"),
        Output(ids.MS_REASON, "value"),
        Input(ids.MS_NEW, "n_clicks"),
        Input(ids.MS_EDIT, "n_clicks"),
        Input(ids.MS_ACHIEVE, "n_clicks"),
        Input(ids.MS_REBASELINE, "n_clicks"),
        Input(ids.MS_CANCEL, "n_clicks"),
        State(ids.MS_GRID, "selectedRows"),
        prevent_initial_call=True,
    )
    def open_dialog(_new, _edit, _achieve, _rebaseline, _cancel, selected):
        trigger = ctx.triggered_id
        if trigger == ids.MS_CANCEL or not ctx.triggered[0]["value"]:
            return (False,) + (no_update,) * 11
        mode = {ids.MS_NEW: "create", ids.MS_EDIT: "edit", ids.MS_ACHIEVE: "achieve",
                ids.MS_REBASELINE: "rebaseline"}[trigger]  # fmt: skip
        selected_ids = [int(r["id"]) for r in selected or []]
        title, shown, date_label = DIALOG[mode]
        name, description, day = "", "", clock.today().isoformat()
        if mode == "edit" and selected_ids:
            try:
                m = services.milestones.get(selected_ids[0])
            except NotFound:
                return (False,) + (no_update,) * 11
            name, description, day = m.name, m.description or "", m.forecast_date.isoformat()
        hidden = [r not in shown for r in ("name", "description", "date", "reason")]
        state = {"mode": mode, "ids": [] if mode == "create" else selected_ids}
        return (True, title, state, *hidden, date_label, name, description, day, "")

    @app.callback(
        *write_outputs(),
        Output(ids.MS_DIALOG, "is_open", allow_duplicate=True),
        Input(ids.MS_SAVE, "n_clicks"),
        State(ids.MS_DIALOG_MODE, "data"),
        State(ids.MS_NAME, "value"),
        State(ids.MS_DESCRIPTION, "value"),
        State(ids.MS_DATE, "value"),
        State(ids.MS_REASON, "value"),
        State(ids.DATA_VERSION, "data"),
        prevent_initial_call=True,
    )
    def save(n, state, name, description, day, reason, version):
        if not n or not state:
            return (*NO_FEEDBACK, no_update)
        action = dialog_action(state, name, description, day, reason)
        outcome, values = run(services, action, version)
        return (*values, False if outcome.ok else no_update)

    @app.callback(
        *write_outputs(),
        Input(ids.MS_REOPEN, "n_clicks"),
        Input(ids.MS_ARCHIVE, "n_clicks"),
        State(ids.MS_GRID, "selectedRows"),
        State(ids.DATA_VERSION, "data"),
        prevent_initial_call=True,
    )
    def direct(_reopen, _archive, selected, version):
        rows = selected or []
        if not ctx.triggered or not ctx.triggered[0]["value"] or not rows:
            return NO_FEEDBACK
        selected_ids = [int(r["id"]) for r in rows]
        if ctx.triggered_id == ids.MS_REOPEN:
            action = {"kind": "reopen_milestone", "milestone_id": selected_ids[0]}
        elif all(r["archived"] for r in rows):
            action = {"kind": "restore_milestones", "milestone_ids": selected_ids}
        else:
            action = {"kind": "archive_milestones", "milestone_ids": selected_ids}
        _, values = run(services, action, version)
        return values


def dialog_action(state: dict, name, description, day, reason) -> dict[str, Any]:
    """Dialog values -> action (pure; see ``DIALOG`` for the modes)."""
    mode, selected = state.get("mode"), state.get("ids") or []
    if mode == "create":
        return {"kind": "create_milestone", "name": name, "description": description,
                "forecast_date": day}  # fmt: skip
    if mode == "rebaseline":
        return {"kind": "rebaseline_milestones", "milestone_ids": selected, "reason": reason}
    if not selected:
        return {"kind": "none"}
    if mode == "edit":
        return {"kind": "update_milestone", "milestone_id": selected[0], "name": name,
                "description": description, "forecast_date": day, "reason": reason}  # fmt: skip
    if mode == "achieve":
        return {"kind": "achieve_milestone", "milestone_id": selected[0], "achieved_date": day}
    return {"kind": "none"}
