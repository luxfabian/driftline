"""Export to Excel and CSV [NFR-03] (architecture §7.3).

Four tables: tasks, milestones, comments, change_log - archived items
included. The task table contains the import columns (architecture §7.5), so
an exported ``tasks.csv`` can be imported again as is. CSV files are UTF-8
with a byte order mark, so Excel opens umlauts correctly.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

import pandas as pd

from driftline.repo import changelog_repo, comment_repo, label_repo, milestone_repo, task_repo
from driftline.services._base import ServiceBase

LIST_SEPARATOR = ";"  # labels and predecessor ids in one cell (same as import)

TASK_COLUMNS = (
    "id", "title", "description", "status", "priority", "labels", "milestone_id",
    "milestone", "predecessor_ids", "baseline_start", "baseline_end", "forecast_start",
    "forecast_end", "estimated_effort_h", "remaining_effort_h", "at_risk", "last_review_at",
    "created_at", "updated_at", "archived_at",
)  # fmt: skip
MILESTONE_COLUMNS = (
    "id", "name", "description", "status", "baseline_date", "forecast_date", "achieved_date",
    "created_at", "updated_at", "archived_at",
)  # fmt: skip
COMMENT_COLUMNS = ("id", "task_id", "kind", "text", "created_at")
CHANGE_LOG_COLUMNS = (
    "id", "entity_type", "entity_id", "change_kind", "field", "old_value", "new_value",
    "reason", "batch_id", "changed_at",
)  # fmt: skip


class ExportService(ServiceBase):
    def tables(self) -> dict[str, list[dict[str, Any]]]:
        """Table name -> rows (plain values), read in one transaction."""
        with self._read() as conn:
            conn.execute("BEGIN")
            try:
                tasks = task_repo.list_all(conn, include_archived=True)
                milestones = milestone_repo.list_all(conn, include_archived=True)
                labels = {lb.id: lb.name for lb in label_repo.list_all(conn)}
                comments = comment_repo.list_all(conn)
                log = changelog_repo.list_all(conn)
            finally:
                conn.execute("COMMIT")
        ms_names = {m.id: m.name for m in milestones}
        return {
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "description": t.description,
                    "status": t.status.value,
                    "priority": int(t.priority),
                    "labels": LIST_SEPARATOR.join(
                        sorted((labels.get(i, f"#{i}") for i in t.label_ids), key=str.lower)
                    ),
                    "milestone_id": t.milestone_id,
                    "milestone": ms_names.get(t.milestone_id),
                    "predecessor_ids": LIST_SEPARATOR.join(map(str, sorted(t.predecessor_ids))),
                    "baseline_start": t.baseline_start,
                    "baseline_end": t.baseline_end,
                    "forecast_start": t.forecast_start,
                    "forecast_end": t.forecast_end,
                    "estimated_effort_h": t.estimated_effort_h,
                    "remaining_effort_h": t.remaining_effort_h,
                    "at_risk": int(t.at_risk),
                    "last_review_at": t.last_review_at,
                    "created_at": t.created_at,
                    "updated_at": t.updated_at,
                    "archived_at": t.archived_at,
                }
                for t in tasks
            ],
            "milestones": [
                {
                    "id": m.id,
                    "name": m.name,
                    "description": m.description,
                    "status": m.status.value,
                    "baseline_date": m.baseline_date,
                    "forecast_date": m.forecast_date,
                    "achieved_date": m.achieved_date,
                    "created_at": m.created_at,
                    "updated_at": m.updated_at,
                    "archived_at": m.archived_at,
                }
                for m in milestones
            ],
            "comments": [
                {
                    "id": c.id,
                    "task_id": c.task_id,
                    "kind": c.kind.value,
                    "text": c.text,
                    "created_at": c.created_at,
                }
                for c in comments
            ],  # fmt: skip
            "change_log": [
                {
                    "id": e.id,
                    "entity_type": e.entity_type.value,
                    "entity_id": e.entity_id,
                    "change_kind": e.change_kind.value,
                    "field": e.field,
                    "old_value": e.old_value,
                    "new_value": e.new_value,
                    "reason": e.reason,
                    "batch_id": e.batch_id,
                    "changed_at": e.changed_at,
                }
                for e in log
            ],
        }

    def to_csv_zip(self) -> bytes:
        """ZIP with tasks.csv, milestones.csv, comments.csv, change_log.csv."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, rows in self.tables().items():
                archive.writestr(f"{name}.csv", _csv(rows, COLUMNS[name]))
        return buffer.getvalue()

    def to_excel(self) -> bytes:
        """One worksheet per table; dates as Excel dates, timestamps as ISO text."""
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            for name, rows in self.tables().items():
                frame = pd.DataFrame(
                    [{k: _excel_value(r[k]) for k in COLUMNS[name]} for r in rows],
                    columns=list(COLUMNS[name]),
                )
                frame.to_excel(writer, sheet_name=name, index=False)
                sheet = writer.sheets[name]
                sheet.freeze_panes = "A2"
                for i, column in enumerate(COLUMNS[name], start=1):
                    width = max([len(column), *(len(str(r[column] or "")) for r in rows[:200])])
                    sheet.column_dimensions[sheet.cell(1, i).column_letter].width = min(
                        width + 2, 60
                    )
                    for cell in sheet[sheet.cell(1, i).column_letter][1:]:
                        if isinstance(cell.value, date | datetime):
                            cell.number_format = "yyyy-mm-dd"
        return buffer.getvalue()


COLUMNS: dict[str, Sequence[str]] = {
    "tasks": TASK_COLUMNS,
    "milestones": MILESTONE_COLUMNS,
    "comments": COMMENT_COLUMNS,
    "change_log": CHANGE_LOG_COLUMNS,
}


def _csv(rows: list[dict[str, Any]], columns: Sequence[str]) -> bytes:
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\r\n")
    writer.writerow(columns)
    for r in rows:
        writer.writerow([_text(r[c]) for c in columns])
    return text.getvalue().encode("utf-8-sig")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _excel_value(value: Any) -> Any:
    """Excel has no time zones: timestamps become ISO text, plain dates stay dates."""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value
