"""SQLite connections and transactions (architecture §4.3).

Connection policy: one connection per callback invocation (open -> use ->
close). Never share a connection between threads.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a connection with foreign keys on and ``sqlite3.Row`` rows.

    Pass ``":memory:"`` in tests. The connection is in autocommit mode
    (``isolation_level=None``); use :func:`transaction` for every write.
    """
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """``BEGIN IMMEDIATE`` ... ``COMMIT``; ``ROLLBACK`` on any exception, then re-raise.

    Transactions do not nest: one service method = one transaction (P3).
    """
    if conn.in_transaction:
        raise RuntimeError("transaction() does not nest; a transaction is already open")
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
