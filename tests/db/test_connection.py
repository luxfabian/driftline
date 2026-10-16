from __future__ import annotations

import sqlite3
import unittest

from pmtool.db.connection import connect, transaction
from tests.helpers import insert_task, memory_db


class ConnectionTest(unittest.TestCase):
    def test_foreign_keys_on_and_row_factory(self):
        conn = connect(":memory:")
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertIs(conn.row_factory, sqlite3.Row)

    def test_transaction_commits(self):
        conn = memory_db()
        with transaction(conn):
            insert_task(conn)
        self.assertFalse(conn.in_transaction)
        self.assertEqual(conn.execute("SELECT count(*) FROM task").fetchone()[0], 1)

    def test_transaction_rolls_back_and_reraises(self):
        conn = memory_db()
        with self.assertRaises(ValueError):
            with transaction(conn):
                insert_task(conn)
                raise ValueError("boom")
        self.assertFalse(conn.in_transaction)
        self.assertEqual(conn.execute("SELECT count(*) FROM task").fetchone()[0], 0)

    def test_constraint_failure_rolls_back_earlier_writes(self):
        conn = memory_db()
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(conn):
                insert_task(conn)
                insert_task(conn, priority=9)
        self.assertEqual(conn.execute("SELECT count(*) FROM task").fetchone()[0], 0)

    def test_transactions_do_not_nest(self):
        conn = memory_db()
        with transaction(conn):
            with self.assertRaises(RuntimeError):
                with transaction(conn):
                    pass


if __name__ == "__main__":
    unittest.main()
