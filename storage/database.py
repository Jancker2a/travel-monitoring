"""
storage/database.py — SQLite connection manager and database lifecycle.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional, Union

from storage.schema import CREATE_TABLES_SQL, SCHEMA_VERSION

logger = logging.getLogger("storage.database")

DEFAULT_DB_PATH = Path("data/travel_monitor.db")


class TravelDatabase:
    """Manages SQLite connection lifecycle, pragmas, and schema migrations."""

    def __init__(self, db_path: Union[str, Path] = DEFAULT_DB_PATH):
        self.db_path = str(db_path)
        self._is_memory = self.db_path == ":memory:"
        if not self._is_memory:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def get_connection(self) -> sqlite3.Connection:
        """Creates a configured connection with optimal pragmas."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=15.0,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode, transactions managed explicitly
        )
        conn.row_factory = sqlite3.Row

        # Performance pragmas
        if not self._is_memory:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 10000;")
        conn.execute("PRAGMA cache_size = -64000;")  # 64 MB cache
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Provides a safe atomic transaction context."""
        conn = self.get_connection()
        try:
            conn.execute("BEGIN;")
            cursor = conn.cursor()
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize_database(self) -> None:
        """Creates tables and sets schema version if not initialized."""
        conn = self.get_connection()
        try:
            conn.executescript(CREATE_TABLES_SQL)
            conn.execute(
                "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('schema_version', ?);",
                (str(SCHEMA_VERSION),),
            )
            conn.commit()
        finally:
            conn.close()
        logger.debug("Database initialized at %s (schema v%s)", self.db_path, SCHEMA_VERSION)
