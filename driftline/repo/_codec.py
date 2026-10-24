"""Conversion between Python values and their stored text/integer form.

data_model_spec §1 (column types) and §3.8 (change_log value encoding).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any


def to_db(value: Any) -> Any:
    """Python value -> SQLite parameter."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):  # check before date: datetime is a date
        return format_timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware [NFR-06]")
    return value.isoformat(timespec="seconds")


def encode_log_value(value: Any) -> str | None:
    """Encoding for change_log old_value/new_value (data_model_spec §3.8)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, datetime):
        return format_timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int | float):
        return repr(float(value))
    return str(value)


def parse_date(text: str | None) -> date | None:
    return None if text is None else date.fromisoformat(text)


def parse_timestamp(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)


def placeholders(n: int) -> str:
    return ", ".join("?" for _ in range(n))
