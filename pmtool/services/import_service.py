"""CSV import of tasks [NFR-08] (architecture §7.5).

Format: UTF-8 (a byte order mark is fine), comma-separated, header row.
Required columns: title, forecast_start, forecast_end, estimated_effort_h.
Optional: priority (1-4 or Critical/High/Medium/Low, default 3), labels
(semicolon-separated), description. Other columns are ignored, so an
exported tasks.csv can be imported again.

All-or-nothing: every row is checked first; if any row fails, nothing is
imported and the result lists the line numbers (header = line 1).
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from datetime import date

from pmtool.domain.commands import TaskCreate
from pmtool.domain.enums import Priority
from pmtool.errors import DomainError
from pmtool.services._base import ServiceBase
from pmtool.services.task_service import insert_task

REQUIRED_COLUMNS = ("title", "forecast_start", "forecast_end", "estimated_effort_h")
OPTIONAL_COLUMNS = ("priority", "labels", "description")
LIST_SEPARATOR = ";"
TEMPLATE_ROWS = (
    ("Write project report", "2026-11-02", "2026-11-06", "12", "2", "work;writing",
     "First full draft"),
    ("Renew passport", "2026-11-09", "2026-11-09", "1.5", "Low", "admin", ""),
)  # fmt: skip


@dataclass(frozen=True)
class RowError:
    line: int  # line number in the file; 1 = header
    message: str


@dataclass(frozen=True)
class ImportResult:
    task_ids: tuple[int, ...] = ()
    errors: tuple[RowError, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def imported(self) -> int:
        return len(self.task_ids)


class ImportService(ServiceBase):
    def from_csv(self, content: bytes) -> ImportResult:
        commands, errors = parse_csv(content)
        if errors:
            return ImportResult(errors=tuple(errors))
        now = self.clock.now()
        ids: list[int] = []
        try:
            with self._write() as conn:  # one transaction: all rows or none
                for line, cmd in commands:
                    try:
                        ids.append(insert_task(conn, cmd, now))
                    except DomainError as exc:
                        raise _RowFailed(line, exc.message) from exc
        except _RowFailed as exc:
            return ImportResult(errors=(RowError(exc.line, exc.message),))
        return ImportResult(task_ids=tuple(ids))

    def template_csv(self) -> bytes:
        """A small example file with every supported column."""
        text = io.StringIO()
        writer = csv.writer(text, lineterminator="\r\n")
        writer.writerow(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)
        writer.writerows(TEMPLATE_ROWS)
        return text.getvalue().encode("utf-8-sig")


class _RowFailed(Exception):
    def __init__(self, line: int, message: str) -> None:
        super().__init__(message)
        self.line, self.message = line, message


def parse_csv(content: bytes) -> tuple[list[tuple[int, TaskCreate]], list[RowError]]:
    """Rows -> (line, TaskCreate) pairs plus every problem found (pure, no DB)."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], [RowError(1, "The file is not UTF-8 text. Save it as CSV UTF-8.")]
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header:
        return [], [RowError(1, "The file is empty.")]
    columns = [h.strip().lower() for h in header]
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        return [], [RowError(1, f"Missing column(s): {', '.join(missing)}.")]

    commands: list[tuple[int, TaskCreate]] = []
    errors: list[RowError] = []
    for values in reader:
        line = reader.line_num
        if not any(v.strip() for v in values):
            continue  # blank line
        row = {c: (values[i].strip() if i < len(values) else "") for i, c in enumerate(columns)}
        problems: list[str] = []
        title = row["title"]
        if not title:
            problems.append("title is empty")
        start = _date(row["forecast_start"], "forecast_start", problems)
        end = _date(row["forecast_end"], "forecast_end", problems)
        if start and end and end < start:
            problems.append("forecast_end is before forecast_start")
        effort = _effort(row["estimated_effort_h"], problems)
        priority = _priority(row.get("priority", ""), problems)
        if problems:
            errors.append(RowError(line, "; ".join(problems)))
            continue
        labels = tuple(x.strip() for x in row.get("labels", "").split(LIST_SEPARATOR) if x.strip())
        commands.append(
            (
                line,
                TaskCreate(
                    title=title,
                    forecast_start=start,
                    forecast_end=end,
                    estimated_effort_h=effort,
                    description=row.get("description") or None,
                    priority=priority,
                    label_names=labels,
                ),
            )
        )
    if not commands and not errors:
        errors.append(RowError(1, "The file has a header but no tasks."))
    return commands, errors


def _date(value: str, column: str, problems: list[str]) -> date | None:
    if not value:
        problems.append(f"{column} is empty")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        problems.append(f"{column} '{value}' is not a date (use YYYY-MM-DD)")
        return None


def _effort(value: str, problems: list[str]) -> float | None:
    try:
        number = float(value.replace(",", "."))  # accept a decimal comma
    except ValueError:
        problems.append(f"estimated_effort_h '{value}' is not a number")
        return None
    if not math.isfinite(number) or number < 0:
        problems.append("estimated_effort_h must be 0 or more")
        return None
    return number


def _priority(value: str, problems: list[str]) -> Priority:
    if not value:
        return Priority.MEDIUM
    by_name = {p.label.lower(): p for p in Priority}
    if value.lower() in by_name:
        return by_name[value.lower()]
    try:
        return Priority(int(value))
    except ValueError:
        problems.append(f"priority '{value}' must be 1-4 or Critical/High/Medium/Low")
        return Priority.MEDIUM
