"""Capacity settings, absences and public holidays [WL-01, WL-07, WL-08, NFR-04]."""

from __future__ import annotations

import math
from dataclasses import fields, replace
from datetime import date
from typing import Any

from driftline.domain.models import Absence, Holiday, Settings
from driftline.errors import NotFound, ValidationError
from driftline.repo import calendar_repo, settings_repo
from driftline.services._base import ServiceBase, clean_text

SETTING_NAMES = {f.name for f in fields(Settings)}


class SettingsService(ServiceBase):
    def get(self) -> Settings:
        with self._read() as conn:
            return settings_repo.get(conn)

    def update(self, **values: Any) -> Settings:
        """Validate and store any subset of settings. Returns the new settings."""
        unknown = set(values) - SETTING_NAMES
        if unknown:
            raise ValidationError("WL-01", f"Unknown setting(s): {', '.join(sorted(unknown))}.")
        with self._write() as conn:
            current = settings_repo.get(conn)
            cleaned = {k: _clean(k, v) for k, v in values.items()}
            new = replace(current, **cleaned)
            if new.load_amber_max < new.load_green_max:
                raise ValidationError(
                    "WL-07", "The amber threshold must not be below the green threshold."
                )
            settings_repo.update(conn, cleaned)
            return new

    # --- absences -------------------------------------------------------------

    def list_absences(self) -> list[Absence]:
        with self._read() as conn:
            return calendar_repo.list_absences(conn)

    def add_absence(self, start_date: date, end_date: date, note: str | None = None) -> int:
        if start_date is None or end_date is None:
            raise ValidationError("WL-01", "Absence start and end date are required.")
        if end_date < start_date:
            raise ValidationError("WL-01", "Absence end must not be before its start.")
        with self._write() as conn:
            return calendar_repo.insert_absence(conn, start_date, end_date, clean_text(note))

    def remove_absence(self, absence_id: int) -> None:
        with self._write() as conn:
            if not calendar_repo.delete_absence(conn, absence_id):
                raise NotFound("NOT-FOUND", f"Absence {absence_id} does not exist.")

    # --- public holidays --------------------------------------------------------

    def list_holidays(self) -> list[Holiday]:
        with self._read() as conn:
            return calendar_repo.list_holidays(conn)

    def add_holiday(self, day: date, name: str | None = None) -> None:
        if day is None:
            raise ValidationError("WL-01", "Holiday date is required.")
        with self._write() as conn:
            if calendar_repo.holiday_exists(conn, day):
                raise ValidationError("WL-01", f"{day.isoformat()} is already a holiday.")
            calendar_repo.insert_holiday(conn, day, clean_text(name))

    def remove_holiday(self, day: date) -> None:
        with self._write() as conn:
            if not calendar_repo.delete_holiday(conn, day):
                raise NotFound("NOT-FOUND", f"{day.isoformat()} is not a holiday.")


# --- validation per setting (data_model_spec §3.9) -------------------------------


def _clean(name: str, value: Any) -> Any:
    if name == "working_weekdays":
        return _weekdays(value)
    if name in {"weekly_hours", "plannable_fraction", "load_green_max", "load_amber_max"}:
        number = _number(name, value)
        if name == "weekly_hours" and number <= 0:
            raise ValidationError("WL-01", "Weekly working hours must be above 0.")
        if name == "plannable_fraction" and not 0 < number <= 1:
            raise ValidationError("WL-01", "Plannable fraction must be above 0 and at most 1.")
        if name in {"load_green_max", "load_amber_max"} and number <= 0:
            raise ValidationError("WL-07", "Load thresholds must be above 0.")
        return number
    integer = _integer(name, value)
    if name == "default_horizon_weeks" and not 1 <= integer <= 12:
        raise ValidationError("WL-07", "The horizon must be between 1 and 12 weeks.")
    if integer <= 0:
        code = {"stale_after_days": "WL-08", "backup_keep_count": "NFR-04"}.get(name, "SCH-06")
        raise ValidationError(code, f"{name.replace('_', ' ').capitalize()} must be above 0.")
    return integer


def _number(name: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("WL-01", f"{name} must be a number.") from exc
    if not math.isfinite(number):
        raise ValidationError("WL-01", f"{name} must be a finite number.")
    return number


def _integer(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValidationError("WL-01", f"{name} must be a whole number.")
    try:
        number = float(value)
    except ValueError as exc:
        raise ValidationError("WL-01", f"{name} must be a whole number.") from exc
    if not number.is_integer():
        raise ValidationError("WL-01", f"{name} must be a whole number.")
    return int(number)


def _weekdays(value: Any) -> tuple[int, ...]:
    if isinstance(value, str):
        value = [v for v in value.split(",") if v.strip()]
    try:
        days = [int(v) for v in value]
    except (TypeError, ValueError) as exc:
        raise ValidationError("WL-01", "Working weekdays must be numbers 1 (Mon) to 7.") from exc
    if not days:
        raise ValidationError("WL-01", "Select at least one working weekday.")
    if len(set(days)) != len(days) or not all(1 <= d <= 7 for d in days):
        raise ValidationError("WL-01", "Working weekdays must be distinct numbers 1 (Mon) to 7.")
    return tuple(sorted(days))
