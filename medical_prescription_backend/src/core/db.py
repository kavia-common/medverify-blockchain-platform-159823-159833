import sqlite3
from typing import Generator

from src.core.config import get_settings


def _connect() -> sqlite3.Connection:
    """Create a SQLite3 connection with foreign keys enabled and Row factory."""
    db_path = get_settings().SQLITE_DB
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# PUBLIC_INTERFACE
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    FastAPI dependency yielding a SQLite3 connection for the duration of the request.

    Yields:
        sqlite3.Connection with row_factory set to sqlite3.Row

    Ensures:
        - Foreign keys are enforced
        - Connection is closed after request
    """
    conn = _connect()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass
