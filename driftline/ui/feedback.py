"""Shared outputs of every write callback (architecture §9.2, write template).

A write callback lists ``*write_outputs()`` first and returns ``*feedback(...)``
first: success bumps DATA_VERSION and shows a toast, a DomainError shows an
error toast, ConfirmationRequired opens the confirm modal with the action
kept in PENDING_ACTION.
"""

from __future__ import annotations

import logging
from typing import Any

from dash import Output, no_update, set_props

from driftline.errors import DomainError
from driftline.services import Services
from driftline.ui import ids
from driftline.ui.actions import Action, Outcome, execute


def write_outputs() -> list[Output]:
    return [
        Output(ids.DATA_VERSION, "data", allow_duplicate=True),
        Output(ids.TOAST, "is_open", allow_duplicate=True),
        Output(ids.TOAST, "header", allow_duplicate=True),
        Output(ids.TOAST, "children", allow_duplicate=True),
        Output(ids.TOAST, "icon", allow_duplicate=True),
        Output(ids.CONFIRM_MODAL, "is_open", allow_duplicate=True),
        Output(ids.CONFIRM_TEXT, "children", allow_duplicate=True),
        Output(ids.PENDING_ACTION, "data", allow_duplicate=True),
    ]


def feedback(outcome: Outcome, version: int | None) -> tuple[Any, ...]:
    """Values for :func:`write_outputs`, in the same order."""
    if outcome.status == "ok":
        return ((version or 0) + 1, True, "Done", outcome.message, "success", False, "", None)
    if outcome.status == "confirm":
        return (no_update, False, no_update, no_update, no_update, True, outcome.message,
                outcome.action)  # fmt: skip
    return (no_update, True, "Not saved", outcome.message, "danger", no_update, no_update,
            no_update)  # fmt: skip


def run(
    services: Services, action: Action, version: int | None, confirmed: bool = False
) -> tuple[Outcome, tuple[Any, ...]]:
    """Execute ``action`` and return the outcome plus the feedback values."""
    outcome = execute(services, action, confirmed=confirmed)
    return outcome, feedback(outcome, version)


NO_FEEDBACK: tuple[Any, ...] = (no_update,) * len(write_outputs())
_MODAL_OPEN, _PENDING = 5, 7  # positions in write_outputs()


def close_confirm(values: tuple[Any, ...]) -> tuple[Any, ...]:
    """Same feedback, but with the confirm modal closed and no pending action."""
    result = list(values)
    result[_MODAL_OPEN], result[_PENDING] = False, None
    return tuple(result)


logger = logging.getLogger("driftline.ui")


def on_callback_error(err: Exception) -> None:
    """App-wide handler for exceptions no callback caught (``Dash(on_error=...)``).

    Every failure becomes a visible toast instead of a silently stale page; the
    full traceback goes to the log file.
    """
    if isinstance(err, DomainError):
        header, message = "Not saved", err.message
    else:
        logger.exception("Unexpected error in a callback", exc_info=err)
        header = "Something went wrong"
        message = (f"{type(err).__name__}: {err}. "
                   "Details are in the log file (driftline.log).")  # fmt: skip
    set_props(ids.TOAST, {"is_open": True, "header": header, "children": message,
                          "icon": "danger"})  # fmt: skip
