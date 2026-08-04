import contextvars
import os
import sqlite3
from collections.abc import Generator
from pathlib import Path

# 동적 DB 라우팅을 위한 ContextVar (테스트 API 요청 시에만 test_trading.db로 덮어쓰기 위해 사용)
test_db_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "test_db_var", default=None
)


_USE_IN_MEMORY = False
_MEM_DB_URI = "file::memory:?cache=shared"
_keepalive_conn = None  # in-memory DB가 초기화되지 않도록 프로세스 수명 동안 유지하는 커넥션


def get_sqlite_db_path() -> Path | str:
    """Return the SQLite DB file path from env or default location.
    만약 contextvars에 test_db_var가 세팅되어 있다면 해당 경로를 최우선으로 반환합니다.
    """
    test_db = test_db_var.get()
    if test_db:
        return Path(test_db).expanduser().resolve()

    if _USE_IN_MEMORY:
        return _MEM_DB_URI

    configured = os.getenv("SQLITE_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "trading.db"


def connect_sqlite() -> sqlite3.Connection:
    """Create a SQLite connection configured for row access by column name."""
    db_path = get_sqlite_db_path()
    
    if isinstance(db_path, str) and db_path.startswith("file::memory:"):
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
    global _USE_IN_MEMORY, _keepalive_conn
    
    import logging
    logger = logging.getLogger(__name__)

    # 물리적 DB 경로 (초기 데이터 로딩용)
    configured = os.getenv("SQLITE_DB_PATH")
    if configured:
        disk_path = Path(configured).expanduser().resolve()
    else:
        disk_path = Path(__file__).resolve().parents[2] / "data" / "trading.db"
    
    logger.info("Initializing in-memory shared database...")
    # 💡 in-memory DB가 GC에 의해 삭제되지 않도록 프로세스 수명 동안 커넥션을 유지합니다.
    _keepalive_conn = sqlite3.connect(_MEM_DB_URI, uri=True, check_same_thread=False)

    # 물리적 DB가 존재하면 in-memory DB로 데이터를 복사(Load)
    if disk_path.exists():
        logger.info("Loading physical DB into shared memory... This may take a moment.")
        disk_conn = sqlite3.connect(disk_path)
        disk_conn.backup(_keepalive_conn)
        disk_conn.close()
        logger.info("Database loaded into memory successfully.")

    # 이 시점 이후부터 생성되는 모든 커넥션은 in-memory DB를 바라보도록 설정
    _USE_IN_MEMORY = True

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


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency that provides a SQLite connection per request."""
    conn = connect_sqlite()
    try:
        yield conn
    finally:
        conn.close()
