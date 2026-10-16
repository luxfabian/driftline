"""Phase 1 acceptance: the schema applies to an empty DB (architecture §12)."""

from __future__ import annotations

import re
import sqlite3
import unittest
from unittest import mock

from pmtool.db import migrations
from pmtool.db.connection import connect
from pmtool.db.migrations import (
    apply_migrations,
    current_version,
    ensure_settings_row,
    read_schema_sql,
)
from pmtool.domain.enums import (
    ChangeKind,
    CommentKind,
    EntityType,
    MilestoneStatus,
    Priority,
    TaskStatus,
)
from pmtool.domain.models import MILESTONE_LOGGED_FIELDS, TASK_LOGGED_FIELDS, Settings
from tests.helpers import TS, insert_milestone, insert_task, memory_db

EXPECTED_TABLES = {
    "schema_version",
    "app_settings",
    "milestone",
    "task",
    "label",
    "task_label",
    "task_dependency",
    "comment",
    "change_log",
    "absence",
    "public_holiday",
}
EXPECTED_INDEXES = {"ix_change_log_entity", "ix_task_active", "ix_task_ms", "ix_comment_task"}


def _names(conn: sqlite3.Connection, kind: str) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'", (kind,)
    )
    return {r[0] for r in rows}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


class SchemaCreationTest(unittest.TestCase):
    def test_empty_db_gets_full_schema(self):
        conn = connect(":memory:")
        self.assertIsNone(current_version(conn))
        self.assertEqual(apply_migrations(conn), 1)
        self.assertEqual(_names(conn, "table"), EXPECTED_TABLES)
        self.assertTrue(EXPECTED_INDEXES <= _names(conn, "index"))
        self.assertEqual(current_version(conn), 1)

    def test_foreign_keys_still_on_after_schema_script(self):
        conn = memory_db()
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_apply_twice_is_idempotent(self):
        conn = memory_db()
        insert_task(conn)
        self.assertEqual(apply_migrations(conn), 1)
        self.assertEqual(conn.execute("SELECT count(*) FROM task").fetchone()[0], 1)

    def test_settings_row_has_spec_defaults(self):
        conn = memory_db()
        row = dict(conn.execute("SELECT * FROM app_settings").fetchone())
        defaults = Settings()
        self.assertEqual(row["id"], 1)
        self.assertEqual(row["weekly_hours"], defaults.weekly_hours)
        self.assertEqual(
            tuple(int(x) for x in row["working_weekdays"].split(",")), defaults.working_weekdays
        )
        for name in (
            "plannable_fraction",
            "default_horizon_weeks",
            "load_green_max",
            "load_amber_max",
            "stale_after_days",
            "backup_keep_count",
            "top_delayed_n",
        ):
            self.assertEqual(row[name], getattr(defaults, name), name)

    def test_ensure_settings_row_restores_missing_row(self):
        conn = memory_db()
        conn.execute("DELETE FROM app_settings")
        ensure_settings_row(conn)
        ensure_settings_row(conn)
        self.assertEqual(conn.execute("SELECT count(*) FROM app_settings").fetchone()[0], 1)

    def test_newer_db_version_is_refused(self):
        conn = memory_db()
        conn.execute("UPDATE schema_version SET version = 99")
        with self.assertRaisesRegex(RuntimeError, "newer"):
            apply_migrations(conn)


class MigrationMechanismTest(unittest.TestCase):
    def test_pending_migration_runs_and_bumps_version(self):
        conn = memory_db()
        sql = "ALTER TABLE task ADD COLUMN extra TEXT;\nCREATE INDEX ix_extra ON task (extra);"
        with mock.patch.dict(migrations.MIGRATIONS, {2: sql}):
            self.assertEqual(apply_migrations(conn), 2)
        self.assertIn("extra", _columns(conn, "task"))
        self.assertEqual(current_version(conn), 2)

    def test_failing_migration_rolls_back_completely(self):
        conn = memory_db()
        sql = "ALTER TABLE task ADD COLUMN extra TEXT;\nTHIS IS NOT SQL;"
        with mock.patch.dict(migrations.MIGRATIONS, {2: sql}):
            with self.assertRaises(sqlite3.Error):
                apply_migrations(conn)
        self.assertNotIn("extra", _columns(conn, "task"))
        self.assertEqual(current_version(conn), 1)


class ConstraintTest(unittest.TestCase):
    """CHECK and FK constraints are the safety net behind the services (§7.4)."""

    def setUp(self):
        self.conn = memory_db()

    def assert_rejected(self, fn, *args, **kwargs):
        with self.assertRaises(sqlite3.IntegrityError):
            fn(*args, **kwargs)

    def test_valid_task_and_milestone_insert(self):
        ms = insert_milestone(self.conn)
        insert_task(self.conn, milestone_id=ms)

    def test_val01_end_before_start_rejected(self):
        self.assert_rejected(insert_task, self.conn, forecast_end="2026-10-01")
        self.assert_rejected(insert_task, self.conn, baseline_end="2026-10-01")

    def test_val02_negative_effort_rejected(self):
        self.assert_rejected(insert_task, self.conn, estimated_effort_h=-1)
        self.assert_rejected(insert_task, self.conn, remaining_effort_h=-0.5)

    def test_val03_done_requires_zero_remaining(self):
        self.assert_rejected(insert_task, self.conn, status="done", remaining_effort_h=1)
        insert_task(self.conn, status="done", remaining_effort_h=0)

    def test_enum_and_range_checks(self):
        self.assert_rejected(insert_task, self.conn, status="waiting")
        self.assert_rejected(insert_task, self.conn, priority=5)
        self.assert_rejected(insert_task, self.conn, priority=0)
        self.assert_rejected(insert_task, self.conn, at_risk=2)
        self.assert_rejected(insert_task, self.conn, title="   ")

    def test_milestone_achieved_date_consistency(self):
        self.assert_rejected(insert_milestone, self.conn, status="achieved")
        self.assert_rejected(insert_milestone, self.conn, achieved_date="2026-11-01")
        insert_milestone(self.conn, status="achieved", achieved_date="2026-11-01")

    def test_label_name_key_unique(self):
        self.conn.execute("INSERT INTO label (name, name_key) VALUES ('Work', 'work')")
        self.assert_rejected(
            self.conn.execute, "INSERT INTO label (name, name_key) VALUES ('WORK', 'work')"
        )

    def test_val05_self_dependency_rejected(self):
        t = insert_task(self.conn)
        self.assert_rejected(
            self.conn.execute,
            "INSERT INTO task_dependency (predecessor_id, successor_id) VALUES (?, ?)",
            (t, t),
        )

    def test_dependency_to_missing_task_rejected(self):
        t = insert_task(self.conn)
        self.assert_rejected(
            self.conn.execute,
            "INSERT INTO task_dependency (predecessor_id, successor_id) VALUES (?, 999)",
            (t,),
        )

    def test_task_delete_cascades(self):
        a, b = insert_task(self.conn), insert_task(self.conn)
        self.conn.execute("INSERT INTO label (name, name_key) VALUES ('x', 'x')")
        self.conn.execute("INSERT INTO task_label VALUES (?, 1)", (a,))
        self.conn.execute("INSERT INTO task_dependency VALUES (?, ?)", (a, b))
        self.conn.execute(
            "INSERT INTO comment (task_id, kind, text, created_at) VALUES (?, 'note', 'hi', ?)",
            (a, TS),
        )
        self.conn.execute("DELETE FROM task WHERE id = ?", (a,))
        for table in ("task_label", "task_dependency", "comment"):
            n = self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            self.assertEqual(n, 0, table)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM label").fetchone()[0], 1)

    def test_milestone_delete_unlinks_tasks(self):
        ms = insert_milestone(self.conn)
        t = insert_task(self.conn, milestone_id=ms)
        self.conn.execute("DELETE FROM milestone WHERE id = ?", (ms,))
        row = self.conn.execute("SELECT milestone_id FROM task WHERE id = ?", (t,)).fetchone()
        self.assertIsNone(row[0])

    def test_rebaseline_requires_reason(self):
        sql = (
            "INSERT INTO change_log (entity_type, entity_id, change_kind, field, "
            "old_value, new_value, reason, changed_at) "
            "VALUES ('task', 1, 'rebaseline', 'baseline_end', '2026-10-16', '2026-10-20', ?, ?)"
        )
        self.assert_rejected(self.conn.execute, sql, (None, TS))
        self.assert_rejected(self.conn.execute, sql, ("  ", TS))
        self.conn.execute(sql, ("Scope change", TS))

    def test_only_one_settings_row(self):
        self.assert_rejected(self.conn.execute, "INSERT INTO app_settings (id) VALUES (2)")

    def test_absence_end_not_before_start(self):
        self.assert_rejected(
            self.conn.execute,
            "INSERT INTO absence (start_date, end_date) VALUES ('2026-12-24', '2026-12-20')",
        )


class SchemaMatchesDomainTest(unittest.TestCase):
    """Enums and logged fields must agree with schema.sql."""

    @classmethod
    def setUpClass(cls):
        cls.sql = read_schema_sql()

    def _check_values(self, column: str) -> set[str]:
        match = re.search(rf"\b{column}\b[^,]*?CHECK \({column} IN \(([^)]*)\)\)", self.sql, re.S)
        self.assertIsNotNone(match, column)
        return {v.strip().strip("'") for v in match.group(1).split(",")}

    def test_enum_values_match_check_constraints(self):
        status_values = re.findall(r"CHECK \(status IN \(([^)]*)\)\)", self.sql)
        sets = [{v.strip().strip("'") for v in s.split(",")} for s in status_values]
        self.assertIn({s.value for s in MilestoneStatus}, sets)
        self.assertIn({s.value for s in TaskStatus}, sets)
        self.assertEqual(self._check_values("kind"), {k.value for k in CommentKind})
        self.assertEqual(self._check_values("entity_type"), {e.value for e in EntityType})
        self.assertEqual(self._check_values("change_kind"), {c.value for c in ChangeKind})
        self.assertIn("priority BETWEEN 1 AND 4", self.sql)
        self.assertEqual([p.value for p in Priority], [1, 2, 3, 4])

    def test_logged_fields_exist_as_columns(self):
        conn = memory_db()
        self.assertTrue(set(TASK_LOGGED_FIELDS) <= _columns(conn, "task"))
        self.assertTrue(set(MILESTONE_LOGGED_FIELDS) <= _columns(conn, "milestone"))


if __name__ == "__main__":
    unittest.main()
