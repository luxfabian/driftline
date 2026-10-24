"""App shell: navbar, filter panel, page container, stores, toast, modals (§9.1)."""

from __future__ import annotations

from collections.abc import Sequence
from types import ModuleType

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from pmtool.domain.filters import Filter
from pmtool.ui import ids
from pmtool.ui.components import confirm_modal, filter_panel, task_detail, task_form
from pmtool.ui.state import filter_to_store

SIDEBAR_WIDTH = "260px"


def navbar(pages: Sequence[ModuleType]) -> dbc.Navbar:
    links = [dbc.NavItem(dbc.NavLink(p.NAME, href=p.PATH, active="exact")) for p in pages]
    return dbc.Navbar(
        dbc.Container(
            [
                dbc.NavbarBrand("pmtool", href="/", className="fw-bold"),
                dbc.Nav(links, navbar=True, className="me-auto"),
                dbc.Button("+ New task", id=ids.NEW_TASK_BUTTON, color="light", size="sm"),
            ],
            fluid=True,
        ),
        color="primary",
        dark=True,
        className="mb-3",
    )


def stores() -> list:
    return [
        dcc.Location(id=ids.URL),
        dcc.Store(id=ids.FILTER, storage_type="session", data=filter_to_store(Filter())),
        dcc.Store(id=ids.DATA_VERSION, storage_type="memory", data=0),
        dcc.Store(id=ids.LOOKUPS, storage_type="memory"),
        dcc.Store(id=ids.PENDING_ACTION, storage_type="memory"),
        dcc.Store(id=ids.SELECTED_TASK, storage_type="memory"),
        dcc.Store(id=ids.DETAIL_STATE, storage_type="memory"),
    ]


def toast() -> dbc.Toast:
    return dbc.Toast(
        id=ids.TOAST,
        header="",
        is_open=False,
        dismissable=True,
        duration=5000,
        style={"position": "fixed", "top": "70px", "right": "16px", "width": "360px",
               "zIndex": 2000},
    )  # fmt: skip


def shell(pages: Sequence[ModuleType]) -> html.Div:
    sidebar = html.Div(
        filter_panel.layout(),
        id=ids.SIDEBAR,
        className="border-end pe-3 me-3",
        style={"width": SIDEBAR_WIDTH, "flexShrink": 0},
    )
    main = html.Div(dash.page_container, className="flex-grow-1", style={"minWidth": 0})
    return html.Div(
        [
            *stores(),
            navbar(pages),
            html.Div([sidebar, main], className="d-flex px-3"),
            toast(),
            confirm_modal.layout(),
            task_form.modal(),
            task_detail.layout(),
        ]
    )
