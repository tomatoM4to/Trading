import os
import sqlite3
import time

DB_PATH = "data/trading.db"


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    # Ensure foreign keys are off during migration just in case
    conn.execute("PRAGMA foreign_keys = OFF")

    print("Migrating daily_ohlcv...")
    start = time.time()

    # daily_ohlcv
    conn.execute("""
    CREATE TABLE daily_ohlcv_new (
        ticker TEXT NOT NULL,
        date TEXT NOT NULL,
        open INTEGER NOT NULL,
        high INTEGER NOT NULL,
        low INTEGER NOT NULL,
        close INTEGER NOT NULL,
        volume INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        PRIMARY KEY (ticker, date)
    ) WITHOUT ROWID, STRICT
    """)
    conn.execute("INSERT INTO daily_ohlcv_new SELECT * FROM daily_ohlcv")
    conn.execute("DROP TABLE daily_ohlcv")
    conn.execute("ALTER TABLE daily_ohlcv_new RENAME TO daily_ohlcv")

    print(f"Migrated daily_ohlcv in {time.time() - start:.2f}s")

    # minute_ohlcv
    print("Migrating minute_ohlcv...")
    start = time.time()
    conn.execute("""
    CREATE TABLE minute_ohlcv_new (
        ticker TEXT NOT NULL,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        open INTEGER NOT NULL,
        high INTEGER NOT NULL,
        low INTEGER NOT NULL,
        close INTEGER NOT NULL,
        volume INTEGER NOT NULL,
        amount INTEGER,
        PRIMARY KEY (ticker, date, time)
    ) WITHOUT ROWID, STRICT
    """)
    conn.execute("INSERT INTO minute_ohlcv_new SELECT * FROM minute_ohlcv")
    conn.execute("DROP TABLE minute_ohlcv")
    conn.execute("ALTER TABLE minute_ohlcv_new RENAME TO minute_ohlcv")

    print(f"Migrated minute_ohlcv in {time.time() - start:.2f}s")

    conn.commit()

    # VACUUM to shrink size
    print("Vacuuming database...")
    start = time.time()
    conn.execute("VACUUM")
    print(f"Vacuum completed in {time.time() - start:.2f}s")

    conn.close()
    print("Migration complete!")


if __name__ == "__main__":
    migrate()
