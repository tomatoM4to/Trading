import os
import sqlite3
from pathlib import Path
from typing import Generator


def get_sqlite_db_path() -> Path:
    """Return the SQLite DB file path from env or default location."""
    configured = os.getenv("SQLITE_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "trading.db"


def connect_sqlite() -> sqlite3.Connection:
    """Create a SQLite connection configured for row access by column name."""
    db_path = get_sqlite_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # WAL 모드는 동시 읽기/쓰기를 개선하지만, 파일 시스템에 따라 호환성 문제가 있을 수 있습니다.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_sqlite_connection() -> None:
    """Validate SQLite connectivity at startup without creating schema."""
    conn = connect_sqlite()
    conn.close()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency that provides a SQLite connection per request."""
    conn = connect_sqlite()
    try:
        yield conn
    finally:
        conn.close()