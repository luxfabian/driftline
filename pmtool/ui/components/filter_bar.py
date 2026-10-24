"""Filter bar, placed on the pages that filter tasks [FUN-09, FUN-10].

One shared FILTER store (session) is the source of truth, so a filter set on
Tasks also applies on Timeline. Each page shows only the fields that matter
there (``TASK_FIELDS``, ``WORKLOAD_FIELDS``); the rest of the stored filter is
kept as is. When a bar appears, its controls are filled from the store; any
change is merged back into it.
"""

from __future__ import annotations

from collections.abc import Sequence

import dash_bootstrap_components as dbc
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update

from pmtool.domain.enums import Priority, TaskStatus
from pmtool.domain.filters import Filter
from pmtool.services import Services
from pmtool.ui import ids
from pmtool.ui.formatting import milestone_options
from pmtool.ui.state import filter_from_store, filter_to_store, merge_into_store

MAIN_FIELDS = ("labels", "milestone_ids", "priorities", "statuses")
MORE_FIELDS = ("label_mode", "date_from", "date_to", "at_risk_only", "include_archived")
TASK_FIELDS = MAIN_FIELDS + MORE_FIELDS
WORKLOAD_FIELDS = ("labels", "milestone_ids", "priorities", "label_mode", "at_risk_only")

_TOGGLES = {"inputClassName": "btn-check", "labelClassName": "btn btn-outline-secondary btn-sm",
            "labelCheckedClassName": "active", "className": "pm-seg"}  # fmt: skip


def layout(page: str, fields: Sequence[str] = TASK_FIELDS) -> html.Div:
    """Compact bar: main fields in one row, the rest behind "More filters"."""
    main = [_control(f) for f in MAIN_FIELDS if f in fields]
    more = [_control(f) for f in MORE_FIELDS if f in fields]
    row = [*main]
    if more:
        row.append(dbc.Button("More filters", id=ids.FILTER_MORE, color="link", size="sm"))
    row.append(dbc.Button("Reset", id=ids.FILTER_RESET, color="link", size="sm",
                          className="text-muted"))  # fmt: skip
    children = [html.Div(row, className="pm-filterbar")]
    if more:
        children.append(dbc.Collapse(html.Div(more, className="pm-filter-more"),
                                     id=ids.FILTER_MORE_PANEL, is_open=False))  # fmt: skip
    return html.Div(children, id=ids.filter_bar(page))


def _control(field: str):
    cid = ids.filter_ctl(field)
    match field:
        case "labels":
            return dcc.Dropdown(id=cid, multi=True, placeholder="All labels",
                                className="pm-filter-wide")  # fmt: skip
        case "milestone_ids":
            return dcc.Dropdown(id=cid, multi=True, placeholder="All milestones",
                                className="pm-filter-wide")  # fmt: skip
        case "priorities":
            return dbc.Checklist(
                id=cid,
                inline=True,
                value=[],
                **_TOGGLES,
                options=[{"label": p.label, "value": int(p)} for p in Priority],
            )
        case "statuses":
            return dbc.Checklist(
                id=cid,
                inline=True,
                value=[],
                **_TOGGLES,
                options=[{"label": s.label, "value": s.value} for s in TaskStatus],
            )
        case "label_mode":
            return dbc.RadioItems(
                id=cid,
                inline=True,
                value="any",
                options=[
                    {"label": "Any of the labels", "value": "any"},
                    {"label": "All of them", "value": "all"},
                ],
            )
        case "date_from":
            return html.Div(
                [
                    html.Span("Dates from", className="me-2 text-muted"),
                    dbc.Input(id=cid, type="date", size="sm"),
                ],
                className="d-flex align-items-center",
            )
        case "date_to":
            return html.Div(
                [
                    html.Span("to", className="me-2 text-muted"),
                    dbc.Input(id=cid, type="date", size="sm"),
                ],
                className="d-flex align-items-center",
            )
        case "at_risk_only":
            return dbc.Switch(id=cid, label="At risk only", value=False, className="mb-0")
        case "include_archived":
            return dbc.Switch(id=cid, label="Include archived", value=False, className="mb-0")
    raise ValueError(f"unknown filter field {field!r}")  # fmt: skip


def more_count(store: dict | None) -> int:
    """How many of the "More filters" fields differ from the default (for the button)."""
    current, default = filter_to_store(filter_from_store(store)), filter_to_store(Filter())
    return sum(current[f] != default[f] for f in MORE_FIELDS)


def register_callbacks(app: Dash, services: Services) -> None:
    @app.callback(
        Output({"type": ids.FILTER_CTL, "field": ALL}, "value"),
        Input({"type": ids.FILTER_BAR, "page": ALL}, "id"),
        State(ids.FILTER, "data"),
    )
    def load(_bars, store):
        """A bar appeared: show the stored filter in its controls."""
        values = filter_to_store(filter_from_store(store))
        return [values[o["id"]["field"]] for o in ctx.outputs_list]

    @app.callback(
        Output(ids.FILTER, "data"),
        Input({"type": ids.FILTER_CTL, "field": ALL}, "value"),
        State(ids.FILTER, "data"),
        prevent_initial_call=True,
    )
    def update(values, store):
        changes = {i["id"]["field"]: v for i, v in zip(ctx.inputs_list[0], values, strict=True)}
        merged = merge_into_store(store, changes)
        return no_update if merged == store else merged

    @app.callback(
        Output(ids.FILTER, "data", allow_duplicate=True),
        Output({"type": ids.FILTER_CTL, "field": ALL}, "value", allow_duplicate=True),
        Input(ids.FILTER_RESET, "n_clicks"),
        prevent_initial_call=True,
    )
    def reset(n):
        if not n:
            return no_update, [no_update] * len(ctx.outputs_list[1])
        default = filter_to_store(Filter())
        return default, [default[o["id"]["field"]] for o in ctx.outputs_list[1]]

    @app.callback(
        Output(ids.filter_ctl("labels"), "options"),
        Output(ids.filter_ctl("milestone_ids"), "options"),
        Input(ids.LOOKUPS, "data"),
    )
    def options(lookup):
        labels = [{"label": lb["name"], "value": lb["id"]}
                  for lb in (lookup or {}).get("label_items", [])]  # fmt: skip
        return labels, [{**o, "disabled": False} for o in milestone_options(lookup)]

    @app.callback(
        Output(ids.FILTER_MORE_PANEL, "is_open"),
        Input(ids.FILTER_MORE, "n_clicks"),
        State(ids.FILTER_MORE_PANEL, "is_open"),
        prevent_initial_call=True,
    )
    def toggle_more(_n, is_open):
        return not is_open

    @app.callback(Output(ids.FILTER_MORE, "children"), Input(ids.FILTER, "data"))
    def more_label(store):
        n = more_count(store)
        return (
            ["More filters", html.Span(str(n), className="pm-filter-count")]
            if n
            else ("More filters")
        )
