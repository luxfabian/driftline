"""Global filter panel [FUN-09, FUN-10] (architecture §9.1).

Controls -> FILTER store. Control values persist per browser session, so the
filter survives page changes and reloads. Hidden on the Settings page.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, dcc, html

from pmtool.domain.enums import TaskStatus
from pmtool.domain.filters import OPEN_STATUSES
from pmtool.services import Services
from pmtool.ui import ids
from pmtool.ui.formatting import milestone_options, priority_options
from pmtool.ui.state import filter_from_controls, filter_to_store

HIDDEN_ON = ("/settings",)
DEFAULT_STATUSES = [s.value for s in TaskStatus if s in OPEN_STATUSES]
_PERSIST = {"persistence": True, "persistence_type": "session"}


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.H6("Filter", className="mb-0"),
                    dbc.Button("Reset", id=ids.FILTER_RESET, size="sm", color="link"),
                ],
                className="d-flex justify-content-between align-items-center mb-2",
            ),
            _group(
                "Labels",
                dcc.Dropdown(id=ids.FILTER_LABELS, multi=True, placeholder="Any label", **_PERSIST),
                dbc.RadioItems(
                    id=ids.FILTER_LABEL_MODE,
                    options=[
                        {"label": "match any", "value": "any"},
                        {"label": "match all", "value": "all"},
                    ],
                    value="any",
                    inline=True,
                    className="small mt-1",
                    **_PERSIST,
                ),  # fmt: skip
            ),
            _group(
                "Priority",
                dbc.Checklist(
                    id=ids.FILTER_PRIORITIES, options=priority_options(), value=[], **_PERSIST
                ),
            ),
            _group(
                "Status",
                dbc.Checklist(
                    id=ids.FILTER_STATUSES,
                    options=[{"label": s.label, "value": s.value} for s in TaskStatus],
                    value=DEFAULT_STATUSES,
                    **_PERSIST,
                ),
            ),
            _group(
                "Milestones",
                dcc.Dropdown(
                    id=ids.FILTER_MILESTONES, multi=True, placeholder="Any milestone", **_PERSIST
                ),
            ),
            _group(
                "Forecast dates overlap",
                dbc.Input(id=ids.FILTER_DATE_FROM, type="date", size="sm", **_PERSIST),
                dbc.Input(
                    id=ids.FILTER_DATE_TO, type="date", size="sm", className="mt-1", **_PERSIST
                ),
            ),  # fmt: skip
            dbc.Switch(id=ids.FILTER_AT_RISK, label="At risk only", value=False, **_PERSIST),
            dbc.Switch(id=ids.FILTER_ARCHIVED, label="Include archived", value=False, **_PERSIST),
        ],
        className="small",
    )


def _group(title: str, *children) -> html.Div:
    return html.Div([dbc.Label(title, className="fw-semibold mb-1"), *children], className="mb-3")


def register_callbacks(app: Dash, services: Services) -> None:
    @app.callback(
        Output(ids.FILTER, "data"),
        Input(ids.FILTER_LABELS, "value"),
        Input(ids.FILTER_LABEL_MODE, "value"),
        Input(ids.FILTER_PRIORITIES, "value"),
        Input(ids.FILTER_STATUSES, "value"),
        Input(ids.FILTER_AT_RISK, "value"),
        Input(ids.FILTER_MILESTONES, "value"),
        Input(ids.FILTER_DATE_FROM, "value"),
        Input(ids.FILTER_DATE_TO, "value"),
        Input(ids.FILTER_ARCHIVED, "value"),
    )
    def update_filter(*values):
        return filter_to_store(filter_from_controls(*values))

    @app.callback(
        Output(ids.FILTER_LABELS, "value"),
        Output(ids.FILTER_LABEL_MODE, "value"),
        Output(ids.FILTER_PRIORITIES, "value"),
        Output(ids.FILTER_STATUSES, "value"),
        Output(ids.FILTER_AT_RISK, "value"),
        Output(ids.FILTER_MILESTONES, "value"),
        Output(ids.FILTER_DATE_FROM, "value"),
        Output(ids.FILTER_DATE_TO, "value"),
        Output(ids.FILTER_ARCHIVED, "value"),
        Input(ids.FILTER_RESET, "n_clicks"),
        prevent_initial_call=True,
    )
    def reset(_n):
        return [], "any", [], DEFAULT_STATUSES, False, [], None, None, False

    @app.callback(
        Output(ids.FILTER_LABELS, "options"),
        Output(ids.FILTER_MILESTONES, "options"),
        Input(ids.LOOKUPS, "data"),
    )
    def options(lookup):
        labels = [{"label": lb["name"], "value": lb["id"]}
                  for lb in (lookup or {}).get("label_items", [])]  # fmt: skip
        milestones = [{**o, "disabled": False} for o in milestone_options(lookup)]
        return labels, milestones

    @app.callback(Output(ids.SIDEBAR, "hidden"), Input(ids.URL, "pathname"))
    def hide_on_settings(pathname):
        return (pathname or "/").rstrip("/") in HIDDEN_ON
