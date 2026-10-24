"""Confirmation dialog for R-05 / R-11 (architecture §9.2).

"Yes" repeats the pending action with ``confirmed=True``; "No" drops it.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import Dash, Input, State, ctx

from pmtool.services import Services
from pmtool.ui import ids
from pmtool.ui.feedback import NO_FEEDBACK, close_confirm, run, write_outputs


def layout() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Please confirm"), close_button=False),
            dbc.ModalBody(id=ids.CONFIRM_TEXT),
            dbc.ModalFooter(
                [
                    dbc.Button("No", id=ids.CONFIRM_NO, color="secondary", outline=True),
                    dbc.Button("Yes", id=ids.CONFIRM_YES, color="primary"),
                ]
            ),
        ],
        id=ids.CONFIRM_MODAL,
        is_open=False,
        backdrop="static",
    )


def register_callbacks(app: Dash, services: Services) -> None:
    @app.callback(
        *write_outputs(),
        Input(ids.CONFIRM_YES, "n_clicks"),
        Input(ids.CONFIRM_NO, "n_clicks"),
        State(ids.PENDING_ACTION, "data"),
        State(ids.DATA_VERSION, "data"),
        prevent_initial_call=True,
    )
    def answer(_yes, _no, pending, version):
        if ctx.triggered_id == ids.CONFIRM_NO or not pending:
            return close_confirm(NO_FEEDBACK)
        _, values = run(services, pending, version, confirmed=True)
        return close_confirm(values)
