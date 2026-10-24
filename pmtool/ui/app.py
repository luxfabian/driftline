"""Dash application factory (architecture §9)."""

from __future__ import annotations

from pathlib import Path

import dash
from dash import Dash, Input, Output

from pmtool.services import Services
from pmtool.ui import ids
from pmtool.ui.components import confirm_modal, filter_panel, task_detail, task_form
from pmtool.ui.feedback import on_callback_error
from pmtool.ui.formatting import lookups
from pmtool.ui.layout import shell
from pmtool.ui.pages import dashboard, milestones, settings, tasks, timeline, workload

# Navbar order (architecture §9.1).
PAGES = (dashboard, tasks, timeline, milestones, workload, settings)

# Bootstrap's CSS is served from here, so the app runs without internet [NFR-01].
ASSETS_DIR = Path(__file__).parent / "assets"


def create_app(services: Services) -> Dash:
    app = Dash(
        __name__,
        use_pages=True,
        pages_folder="",
        assets_folder=str(ASSETS_DIR),
        serve_locally=True,
        suppress_callback_exceptions=True,  # page components appear after navigation
        title="pmtool",
        update_title=None,
        on_error=on_callback_error,  # any uncaught error -> toast + log (phase 7)
    )
    for order, page in enumerate(PAGES):
        dash.register_page(
            page.__name__,
            path=page.PATH,
            name=page.NAME,
            title=f"{page.NAME} · pmtool",
            order=order,
            layout=page.layout,
        )
    app.layout = shell(PAGES)

    _register_lookups(app, services)
    filter_panel.register_callbacks(app, services)
    confirm_modal.register_callbacks(app, services)
    task_form.register_callbacks(app, services)
    task_detail.register_callbacks(app, services)
    for page in PAGES:
        if hasattr(page, "register_callbacks"):
            page.register_callbacks(app, services)
    return app


def _register_lookups(app: Dash, services: Services) -> None:
    @app.callback(Output(ids.LOOKUPS, "data"), Input(ids.DATA_VERSION, "data"))
    def refresh(_version):
        return lookups(services.snapshot.load(include_archived=True))
