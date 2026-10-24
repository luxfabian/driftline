"""Task form fields and the "New task" modal [FUN-01, FUN-05, DAT-04].

``form_fields`` builds the fields for either form (``ids.NEW_FORM`` or
``ids.EDIT_FORM``); the edit form adds remaining effort, status and reasons.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

from pmtool.domain.enums import Priority
from pmtool.services import Services
from pmtool.ui import ids
from pmtool.ui.feedback import NO_FEEDBACK, run, write_outputs
from pmtool.ui.formatting import (
    label_options,
    milestone_options,
    priority_options,
    status_options,
    task_options,
)


def form_fields(form: ids.TaskFormIds, edit: bool) -> html.Div:
    rows = [
        _field("Title", dbc.Input(id=form.title, type="text", maxLength=200)),
        _field("Description", dbc.Textarea(id=form.description, rows=2)),
        dbc.Row(
            [
                dbc.Col(_field("Forecast start", dbc.Input(id=form.start, type="date"))),
                dbc.Col(_field("Forecast end", dbc.Input(id=form.end, type="date"))),
            ]
        ),
        dbc.Row(
            [
                dbc.Col(
                    _field(
                        "Estimated effort (h)",
                        dbc.Input(id=form.estimated, type="number", min=0, step=0.5),
                    )
                ),
                dbc.Col(
                    _field(
                        "Remaining effort (h)",
                        dbc.Input(id=form.remaining, type="number", min=0, step=0.5),
                    )
                )
                if edit
                else None,
                dbc.Col(
                    _field(
                        "Priority",
                        dbc.Select(id=form.priority, options=priority_options(as_text=True)),
                    )
                ),
            ]  # fmt: skip
        ),
    ]
    if edit:
        rows.append(
            dbc.Row(
                [
                    dbc.Col(_field("Status", dbc.Select(id=form.status, options=status_options()))),
                    dbc.Col(
                        _field(
                            "Reason for Blocked",
                            dbc.Input(
                                id=form.status_reason,
                                type="text",
                                placeholder="required when setting Blocked",
                            ),
                        )
                    ),
                ]  # fmt: skip
            )
        )
    rows += [
        _field(
            "Labels",
            dcc.Dropdown(id=form.labels, multi=True, placeholder="Type to search or add"),
        ),
        _field("Milestone", dcc.Dropdown(id=form.milestone, placeholder="No milestone")),
    ]
    if edit:
        rows.append(
            _field("Change reason (optional, stored in history)",
                   dbc.Input(id=form.reason, type="text"))
        )  # fmt: skip
    else:
        rows.append(
            _field("Predecessors", dcc.Dropdown(id=form.predecessors, multi=True,
                                                placeholder="None"))
        )  # fmt: skip
    return html.Div(rows)


def _field(label: str, control) -> html.Div:
    return html.Div([dbc.Label(label, className="small mb-1"), control], className="mb-2")


def modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("New task")),
            dbc.ModalBody(form_fields(ids.NEW_FORM, edit=False)),
            dbc.ModalFooter(
                [
                    dbc.Button("Cancel", id=ids.NEW_TASK_CANCEL, color="secondary", outline=True),
                    dbc.Button("Create task", id=ids.NEW_TASK_SAVE, color="primary"),
                ]
            ),
        ],
        id=ids.NEW_TASK_MODAL,
        is_open=False,
        size="lg",
    )


def register_label_options(app: Dash, form: ids.TaskFormIds) -> None:
    """Offer existing labels plus the typed text as a new label (DAT-04)."""

    @app.callback(
        Output(form.labels, "options"),
        Input(form.labels, "search_value"),
        Input(ids.LOOKUPS, "data"),
        State(form.labels, "value"),
    )
    def options(typed, lookup, selected):
        return label_options(lookup, selected, typed)


def register_callbacks(app: Dash, services: Services) -> None:
    form = ids.NEW_FORM
    register_label_options(app, form)

    @app.callback(
        Output(form.milestone, "options"),
        Output(form.predecessors, "options"),
        Input(ids.LOOKUPS, "data"),
    )
    def lookups(lookup):
        return milestone_options(lookup), task_options(lookup)

    @app.callback(
        Output(ids.NEW_TASK_MODAL, "is_open"),
        Output(form.title, "value"),
        Output(form.description, "value"),
        Output(form.start, "value"),
        Output(form.end, "value"),
        Output(form.estimated, "value"),
        Output(form.priority, "value"),
        Output(form.labels, "value"),
        Output(form.milestone, "value"),
        Output(form.predecessors, "value"),
        Input(ids.NEW_TASK_BUTTON, "n_clicks"),
        Input(ids.NEW_TASK_CANCEL, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_or_cancel(_open, _cancel):
        if ctx.triggered_id == ids.NEW_TASK_CANCEL:
            return (False,) + (no_update,) * 9
        today = services.tasks.clock.today().isoformat()
        return True, "", "", today, today, None, str(int(Priority.MEDIUM)), [], None, []

    @app.callback(
        *write_outputs(),
        Output(ids.NEW_TASK_MODAL, "is_open", allow_duplicate=True),
        Input(ids.NEW_TASK_SAVE, "n_clicks"),
        State(form.title, "value"),
        State(form.description, "value"),
        State(form.start, "value"),
        State(form.end, "value"),
        State(form.estimated, "value"),
        State(form.priority, "value"),
        State(form.labels, "value"),
        State(form.milestone, "value"),
        State(form.predecessors, "value"),
        State(ids.DATA_VERSION, "data"),
        prevent_initial_call=True,
    )
    def create(n, title, description, start, end, estimated, priority, labels, milestone,
               predecessors, version):  # fmt: skip
        if not n:
            return (*NO_FEEDBACK, no_update)
        action = {
            "kind": "create_task",
            "title": title,
            "description": description,
            "forecast_start": start,
            "forecast_end": end,
            "estimated_effort_h": estimated,
            "priority": priority,
            "labels": labels or [],
            "milestone_id": milestone,
            "predecessor_ids": predecessors or [],
        }
        outcome, values = run(services, action, version)
        return (*values, False if outcome.ok else no_update)
