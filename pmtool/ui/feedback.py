"""Shared outputs of every write callback (architecture §9.2, write template).

A write callback lists ``*write_outputs()`` first and returns ``*feedback(...)``
first: success bumps DATA_VERSION and shows a toast, a DomainError shows an
error toast, ConfirmationRequired opens the confirm modal with the action
kept in PENDING_ACTION.
"""

from __future__ import annotations

from typing import Any

from dash import Output, no_update

from pmtool.services import Services
from pmtool.ui import ids
from pmtool.ui.actions import Action, Outcome, execute


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
