"""Domain errors shared by services and UI (architecture §4.2)."""

from __future__ import annotations


class DomainError(Exception):
    """Base class. ``code`` names the violated rule (e.g. "VAL-01", "R-05")."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class ValidationError(DomainError):
    """A rule was violated; nothing was written."""


class NotFound(DomainError):
    """The referenced task, milestone or other entity does not exist."""


class ConfirmationRequired(DomainError):
    """The action needs user confirmation (R-05, R-11).

    Nothing was written. The UI shows a modal and repeats the call with
    ``confirmed=True``.
    """
