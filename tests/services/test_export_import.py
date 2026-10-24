"""Export [NFR-03] and CSV import [NFR-08], incl. the phase 6 round trip."""

from __future__ import annotations

import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import openpyxl

from driftline.clock import FixedClock
from driftline.db.connection import connect
from driftline.db.migrations import apply_migrations
from driftline.domain.enums import Priority
from driftline.services import build_services
from driftline.services.import_service import parse_csv
from tests.helpers import T0
from tests.services.base import D, ServiceTestCase

HEADER = "title,forecast_start,forecast_end,estimated_effort_h,priority,labels,description\n"


class ExportTest(ServiceTestCase):
    def setUp(self):
        super().setUp()
        self.ms = self.make_milestone(name="Review")
        self.a = self.make_task(
            title="Bericht schreiben",
            label_names=("work", "Ärger"),
            priority=Priority.HIGH,
            milestone_id=self.ms,
        )
        self.b = self.make_task(title="B", predecessor_ids=(self.a,))
        self.svc.tasks.add_comment(self.a, "Hallo, Welt")
        self.svc.tasks.archive(self.b)

    def zip_rows(self, name):
        archive = zipfile.ZipFile(io.BytesIO(self.svc.export.to_csv_zip()))
        text = archive.read(f"{name}.csv").decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text)))

    def test_csv_zip_contains_all_tables_incl_archived(self):
        archive = zipfile.ZipFile(io.BytesIO(self.svc.export.to_csv_zip()))
        self.assertEqual(
            sorted(archive.namelist()),
            ["change_log.csv", "comments.csv", "milestones.csv", "tasks.csv"],
        )
        tasks = {r["id"]: r for r in self.zip_rows("tasks")}
        self.assertEqual(set(tasks), {str(self.a), str(self.b)})
        a = tasks[str(self.a)]
        self.assertEqual(a["title"], "Bericht schreiben")
        self.assertEqual(a["labels"], "work;Ärger")  # same order as everywhere: str.lower
        self.assertEqual((a["priority"], a["milestone"]), ("2", "Review"))
        self.assertEqual(a["forecast_start"], "2026-10-12")
        self.assertEqual(tasks[str(self.b)]["predecessor_ids"], str(self.a))
        self.assertNotEqual(tasks[str(self.b)]["archived_at"], "")

    def test_csv_has_bom_for_excel(self):
        archive = zipfile.ZipFile(io.BytesIO(self.svc.export.to_csv_zip()))
        self.assertTrue(archive.read("tasks.csv").startswith(b"\xef\xbb\xbf"))

    def test_comments_and_history_exported(self):
        self.assertEqual([r["text"] for r in self.zip_rows("comments")], ["Hallo, Welt"])
        log = self.zip_rows("change_log")
        self.assertIn("archive", {r["change_kind"] for r in log})
        self.assertEqual(len(self.zip_rows("milestones")), 1)

    def test_excel_has_one_sheet_per_table(self):
        book = openpyxl.load_workbook(io.BytesIO(self.svc.export.to_excel()))
        self.assertEqual(book.sheetnames, ["tasks", "milestones", "comments", "change_log"])
        sheet = book["tasks"]
        header = [c.value for c in sheet[1]]
        row = {h: c.value for h, c in zip(header, sheet[2], strict=True)}
        self.assertEqual(row["title"], "Bericht schreiben")
        self.assertEqual(row["forecast_start"].date(), D("2026-10-12"))  # a real Excel date
        self.assertIsInstance(row["created_at"], str)  # timestamps as ISO text (no tz in Excel)


class ImportTest(ServiceTestCase):
    def test_imports_valid_file(self):
        content = (
            HEADER + "Write report,2026-11-02,2026-11-06,12,High,work;Writing,Draft\n"
            'Passport,2026-11-09,2026-11-09,"1,5",,,\n'
        ).encode()
        result = self.svc.importer.from_csv(content)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.imported, 2)
        first = self.svc.tasks.detail(result.task_ids[0])
        self.assertEqual(first.task.priority, Priority.HIGH)
        self.assertEqual(
            sorted((lb.name for lb in first.labels), key=str.lower), ["work", "Writing"]
        )
        self.assertEqual(first.task.description, "Draft")
        second = self.task(result.task_ids[1])
        self.assertEqual((second.estimated_effort_h, second.priority), (1.5, Priority.MEDIUM))
        self.assertEqual(len(self.log("task", result.task_ids[0], "create")), 6)  # R-01

    def test_all_or_nothing_with_line_numbers(self):
        content = (
            HEADER + "Good,2026-11-02,2026-11-06,1,,,\n"
            ",2026-11-02,2026-11-06,1,,,\n"
            "Bad dates,2026-11-09,2026-11-01,x,7,,\n"
        ).encode()
        result = self.svc.importer.from_csv(content)
        self.assertFalse(result.ok)
        self.assertEqual([e.line for e in result.errors], [3, 4])
        self.assertIn("title is empty", result.errors[0].message)
        self.assertIn("before forecast_start", result.errors[1].message)
        self.assertIn("not a number", result.errors[1].message)
        self.assertIn("priority", result.errors[1].message)
        self.assertEqual(self.query("SELECT count(*) AS n FROM task")[0]["n"], 0)

    def test_header_problems(self):
        self.assertIn(
            "Missing column", parse_csv(b"title,forecast_start\nx,2026-01-01\n")[1][0].message
        )
        self.assertIn("empty", parse_csv(b"")[1][0].message)
        self.assertIn("no tasks", parse_csv(HEADER.encode())[1][0].message)
        self.assertIn("UTF-8", parse_csv("title\nÄ".encode("latin-1"))[1][0].message)

    def test_header_is_case_insensitive_and_extra_columns_ignored(self):
        content = (
            b"Title,FORECAST_START,forecast_end,estimated_effort_h,status\n"
            b"X,2026-11-02,2026-11-03,2,done\n"
        )
        result = self.svc.importer.from_csv(content)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(self.task(result.task_ids[0]).status.value, "planned")

    def test_template_imports(self):
        result = self.svc.importer.from_csv(self.svc.importer.template_csv())
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.imported, 2)


class RoundTripTest(ServiceTestCase):
    """Phase 6 acceptance: export -> fresh DB -> import tasks."""

    def test_export_then_import_into_fresh_database(self):
        self.make_task(
            title="Alpha",
            label_names=("Work", "home"),
            priority=Priority.CRITICAL,
            description="First",
            estimated_effort_h=7.5,
        )
        self.make_task(title="Beta", forecast_start=D("2026-11-02"), forecast_end=D("2026-11-20"))
        archive = zipfile.ZipFile(io.BytesIO(self.svc.export.to_csv_zip()))

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "fresh.db"
            conn = connect(db)
            apply_migrations(conn)
            conn.close()
            fresh = build_services(db, FixedClock(T0))
            result = fresh.importer.from_csv(archive.read("tasks.csv"))
            self.assertTrue(result.ok, result.errors)

            def plan(services):
                snap = services.snapshot.load()
                names = {lb.id: lb.name for lb in snap.labels}
                return sorted(
                    (
                        t.title,
                        t.description,
                        t.forecast_start,
                        t.forecast_end,
                        t.estimated_effort_h,
                        int(t.priority),
                        tuple(sorted(names[i] for i in t.label_ids)),
                    )
                    for t in snap.tasks
                )

            self.assertEqual(plan(fresh), plan(self.svc))


if __name__ == "__main__":
    unittest.main()
