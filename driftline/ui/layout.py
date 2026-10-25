"""App shell: navbar, page container, stores, toast, modals (§9.1).

Filters are not part of the shell: pages that filter tasks place a filter
bar (``components/filter_bar.py``) above their content.
"""

from __future__ import annotations

from collections.abc import Sequence
from types import ModuleType

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from driftline.domain.filters import Filter
from driftline.ui import ids, theme
from driftline.ui.components import confirm_modal, task_detail, task_form
from driftline.ui.state import filter_to_store


def navbar(pages: Sequence[ModuleType]) -> dbc.Navbar:
    links = [dbc.NavItem(dbc.NavLink(p.NAME, href=p.PATH, active="exact")) for p in pages]
    return dbc.Navbar(
        dbc.Container(
            [
                dbc.NavbarBrand("Driftline", href="/"),
                dbc.Nav(links, navbar=True, className="me-auto"),
                dbc.Button("+ New task", id=ids.NEW_TASK_BUTTON, size="sm", className="btn-new"),
            ],
            fluid=True,
            className="px-4",
        ),
        className="pm-navbar",
        dark=True,
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
        style={"position": "fixed", "top": "72px", "right": "20px", "width": "360px",
               "zIndex": 2000},
    )  # fmt: skip


def shell(pages: Sequence[ModuleType], palette: theme.Palette | None = None) -> html.Div:
    """The page frame. Its theme class selects the colours of ``assets/themes.css``."""
    palette = palette or theme.active()
    return html.Div(
        [
            *stores(),
            navbar(pages),
            html.Main(dash.page_container, className="pm-page"),
            toast(),
            confirm_modal.layout(),
            task_form.modal(),
            task_detail.layout(),
            dcc.Store(id=ids.THEME_RELOAD, storage_type="memory"),
        ],
        id=ids.SHELL,
        className=theme.shell_class(palette),
    )


def page_header(title: str, subtitle_id: str | None = None, actions=None) -> html.Div:
    """Title (+ an optional subtitle filled by a callback) left, actions right."""
    left = [html.H1(title, className="pm-title")]
    if subtitle_id:
        left.append(html.Div(id=subtitle_id, className="pm-subtitle"))
    right = html.Div(actions or [], className="d-flex flex-wrap gap-2 align-items-center")
    return html.Div([html.Div(left), right], className="pm-header")
