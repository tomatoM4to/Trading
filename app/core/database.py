import contextvars
import os
import sqlite3
from collections.abc import Generator
from pathlib import Path

# 동적 DB 라우팅을 위한 ContextVar
test_db_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "test_db_var", default=None
)
test_mem_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "test_mem_var", default=None
)


_MA_MEM_DB_URI = "file:ma_db?mode=memory&cache=shared"
DAILY_MA_RETENTION = 301
MINUTE_MA_RETENTION = 391
_keepalive_ma_conn = None  # 이평선(MA) 전용 인메모리 커넥션


def get_sqlite_db_path() -> Path | str:
    """Return the SQLite DB file path from env or default location.
    만약 contextvars에 test_db_var가 세팅되어 있다면 해당 경로를 최우선으로 반환합니다.
    """
    test_mem = test_mem_var.get()
    if test_mem:
        return test_mem

    test_db = test_db_var.get()
    if test_db:
        return Path(test_db).expanduser().resolve()

    configured = os.getenv("SQLITE_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "trading.db"


def connect_sqlite() -> sqlite3.Connection:
    """Create a SQLite connection configured for row access by column name."""
    db_path = get_sqlite_db_path()

    if isinstance(db_path, str) and ("memory" in db_path):
        conn = sqlite3.connect(db_path, uri=True, check_same_thread=False)
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        # WAL 모드는 동시 읽기/쓰기를 개선하지만, 파일 시스템에 따라 호환성 문제가 있을 수 있습니다.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # 💡 모든 연결에 대해 임시 테이블을 메모리에 생성하도록 강제 (OOM 및 디스크 I/O 방지)
    conn.execute("PRAGMA temp_store = MEMORY")

    return conn


def init_sqlite_connection() -> None:
    """Validate SQLite connectivity at startup and create schema."""
    global _keepalive_ma_conn

    import logging

    logger = logging.getLogger(__name__)

    # Shared In-Memory MA DB의 수명을 프로세스 종료까지 유지합니다.
    logger.info("Initializing MA dedicated in-memory database...")
    _keepalive_ma_conn = sqlite3.connect(
        _MA_MEM_DB_URI, uri=True, check_same_thread=False
    )
    _keepalive_ma_conn.execute("PRAGMA temp_store = MEMORY")
    _keepalive_ma_conn.row_factory = sqlite3.Row

    # OHLCV와 종목 정보는 디스크 DB를 정본으로 사용합니다.
    conn = connect_sqlite()
    try:
        # daily_ohlcv 테이블 생성
        conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_ohlcv (
            ticker TEXT NOT NULL,
            date INTEGER NOT NULL,
            open INTEGER NOT NULL,
            high INTEGER NOT NULL,
            low INTEGER NOT NULL,
            close INTEGER NOT NULL,
            volume INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            PRIMARY KEY (ticker, date)
        ) WITHOUT ROWID, STRICT
        """)

        # stock_codes 테이블
        conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_codes (
            ticker TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            market TEXT NOT NULL,
            market_cap REAL,
            total_shares REAL,
            credit_able TEXT,
            margin_rate REAL,
            revenue REAL,
            operating_profit REAL,
            net_income REAL,
            roe REAL,
            is_halted INTEGER,
            is_admin_issue INTEGER,
            is_overheated INTEGER,
            is_warning INTEGER
        ) WITHOUT ROWID, STRICT
        """)

        # minute_ohlcv 테이블 (추후 분봉 적재 스케줄러 용)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS minute_ohlcv (
            ticker TEXT NOT NULL,
            date INTEGER NOT NULL,
            time INTEGER NOT NULL,
            open INTEGER NOT NULL,
            high INTEGER NOT NULL,
            low INTEGER NOT NULL,
            close INTEGER NOT NULL,
            volume INTEGER NOT NULL,
            amount INTEGER,
            PRIMARY KEY (ticker, date, time)
        ) WITHOUT ROWID, STRICT
        """)

        conn.commit()
    finally:
        conn.close()

    # MA 인메모리 DB 스키마 생성
    ma_conn = connect_ma_db()
    try:
        ma_conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_ma (
            ticker TEXT NOT NULL,
            date INTEGER NOT NULL,
            ma5 REAL,
            ma10 REAL,
            ma20 REAL,
            ma60 REAL,
            ma120 REAL,
            ma200 REAL,
            PRIMARY KEY (ticker, date)
        ) WITHOUT ROWID, STRICT
        """)

        ma_conn.execute("""
        CREATE TABLE IF NOT EXISTS minute_ma (
            ticker TEXT NOT NULL,
            date INTEGER NOT NULL,
            time INTEGER NOT NULL,
            ma5 REAL,
            ma10 REAL,
            ma20 REAL,
            ma60 REAL,
            ma120 REAL,
            ma200 REAL,
            PRIMARY KEY (ticker, date, time)
        ) WITHOUT ROWID, STRICT
        """)
        ma_conn.commit()
    finally:
        ma_conn.close()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency that provides a SQLite connection per request."""
    conn = connect_sqlite()
    try:
        yield conn
    finally:
        conn.close()


def connect_ma_db() -> sqlite3.Connection:
    """Create a connection to the MA-dedicated in-memory database."""
    conn = sqlite3.connect(_MA_MEM_DB_URI, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


def get_ma_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency for the MA in-memory database."""
    conn = connect_ma_db()
    try:
        yield conn
    finally:
        conn.close()


def prune_ma_history(
    conn: sqlite3.Connection,
    table_name: str,
    limit: int,
    ticker: str | None = None,
) -> None:
    """Keep only the newest MA rows per ticker without committing."""
    table_keys = {
        "daily_ma": ("ticker", "date"),
        "minute_ma": ("ticker", "date", "time"),
    }
    keys = table_keys.get(table_name)
    if keys is None:
        raise ValueError(f"Unsupported MA table: {table_name}")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("MA retention limit must be a positive integer")

    key_list = ", ".join(keys)
    order_by = "date DESC" if table_name == "daily_ma" else "date DESC, time DESC"
    ticker_filter = "WHERE ticker = ?" if ticker is not None else ""
    params: list[str | int] = [ticker] if ticker is not None else []
    params.append(limit)

    conn.execute(
        f"""
        DELETE FROM {table_name}
        WHERE ({key_list}) IN (
            SELECT {key_list}
            FROM (
                SELECT {key_list},
                       ROW_NUMBER() OVER (
                           PARTITION BY ticker ORDER BY {order_by}
                       ) AS rn
                FROM {table_name}
                {ticker_filter}
            )
            WHERE rn > ?
        )
        """,
        params,
    )


def sync_memory_to_disk(mem_conn: sqlite3.Connection | None = None) -> None:
    """Flush the disk DB WAL, or back up an explicitly supplied test DB."""
    import logging

    logger = logging.getLogger(__name__)

    # Fallback in case custom sched level is not initialized
    log_func = getattr(logger, "sched", logger.info)

    log_func("[DB SYNC] Starting durability synchronization...")

    # 물리적 DB 경로 확보 (테스트 환경 최우선 라우팅)
    test_db = test_db_var.get()
    if test_db:
        disk_path = Path(test_db).expanduser().resolve()
    else:
        configured = os.getenv("SQLITE_DB_PATH")
        if configured:
            disk_path = Path(configured).expanduser().resolve()
        else:
            disk_path = Path(__file__).resolve().parents[2] / "data" / "trading.db"

    try:
        disk_path.parent.mkdir(parents=True, exist_ok=True)
        # WAL 모드 적용된 디스크 커넥션 열기
        disk_conn = sqlite3.connect(disk_path, check_same_thread=False)
        try:
            disk_conn.execute("PRAGMA journal_mode = WAL")
            disk_conn.execute("PRAGMA synchronous = NORMAL")
            if mem_conn is None:
                disk_conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            else:
                # Preserve the explicit in-memory backup path used by integration tests.
                mem_conn.backup(disk_conn, pages=256, sleep=0.001)
        finally:
            disk_conn.close()

        log_func(f"[DB SYNC] Disk durability synchronized: {disk_path.name}")
    except Exception as e:
        logger.error(f"[DB SYNC] Failed to sync to disk: {e}")
        raise
