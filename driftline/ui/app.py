"""Dash application factory (architecture §9)."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import dash
from dash import Dash, Input, Output

from driftline.services import Services
from driftline.ui import ids, theme
from driftline.ui.components import confirm_modal, filter_bar, task_detail, task_form
from driftline.ui.feedback import on_callback_error
from driftline.ui.formatting import lookups
from driftline.ui.layout import shell
from driftline.ui.pages import dashboard, milestones, settings, tasks, timeline, workload

logger = logging.getLogger(__name__)

# Navbar order (architecture §9.1).
PAGES = (dashboard, tasks, timeline, milestones, workload, settings)

# Bootstrap's CSS, the theme and its fonts are served from here, so the app runs
# without internet [NFR-01].
ASSETS_DIR = Path(__file__).parent / "assets"


def create_app(services: Services) -> Dash:
    app = Dash(
        __name__,
        use_pages=True,
        pages_folder="",
        assets_folder=str(ASSETS_DIR),
        serve_locally=True,
        suppress_callback_exceptions=True,  # page components appear after navigation
        title="Driftline",
        update_title=None,
        on_error=on_callback_error,  # any uncaught error -> toast + log (phase 7)
    )
    for order, page in enumerate(PAGES):
        dash.register_page(
            page.__name__,
            path=page.PATH,
            name=page.NAME,
            title=f"{page.NAME} · Driftline",
            order=order,
            layout=page.layout,
        )
    app.layout = lambda: _shell(services)  # per page load: picks up the theme setting

    _register_lookups(app, services)
    # A theme change reloads the page so the shell and every figure pick it up.
    app.clientside_callback(
        "function(key) { if (key) { window.location.reload(); } }",
        Input(ids.THEME_RELOAD, "data"),
        prevent_initial_call=True,
    )
    filter_bar.register_callbacks(app, services)
    confirm_modal.register_callbacks(app, services)
    task_form.register_callbacks(app, services)
    task_detail.register_callbacks(app, services)
    for page in PAGES:
        if hasattr(page, "register_callbacks"):
            page.register_callbacks(app, services)
    return app


def _shell(services: Services):
    try:
        key = services.settings.get().theme
    except sqlite3.Error:  # unreadable database: the callbacks report it, the shell still loads
        logger.exception("Could not read the colour theme; using the default")
        key = None
    return shell(PAGES, theme.use(key))


def _register_lookups(app: Dash, services: Services) -> None:
    @app.callback(Output(ids.LOOKUPS, "data"), Input(ids.DATA_VERSION, "data"))
    def refresh(_version):
        return lookups(services.snapshot.load(include_archived=True))
