"""Injected time source (architecture P7).

This is the only module allowed to read the system clock. Everything else
receives a ``Clock`` and asks it for ``now()`` / ``today()``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time, timezone-aware, in the local zone."""
        ...

    def today(self) -> date:
        """Current local date."""
        ...


class SystemClock:
    """Real time in the local system time zone."""

    def now(self) -> datetime:
        return datetime.now().astimezone().replace(microsecond=0)

    def today(self) -> date:
        return self.now().date()


class FixedClock:
    """Deterministic clock for tests. Time only moves when ``advance`` is called."""

    def __init__(self, now: datetime) -> None:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")
        self._now = now

    def now(self) -> datetime:
        return self._now

    def today(self) -> date:
        return self._now.date()

    def advance(self, **kwargs: float) -> None:
        """Move the clock forward, e.g. ``advance(days=3, hours=2)``."""
        self._now = self._now + timedelta(**kwargs)
