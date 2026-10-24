"""Layout for pages that arrive in a later phase."""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html


def placeholder(name: str, phase: int, content: str) -> html.Div:
    return html.Div(
        [
            html.H4(name),
            dbc.Alert(
                [
                    html.Strong(f"Arrives in phase {phase}. "),
                    content,
                    html.Div(dbc.Button("Go to Tasks", href="/tasks", size="sm", className="mt-2")),
                ],
                color="light",
            ),  # fmt: skip
        ]
    )
