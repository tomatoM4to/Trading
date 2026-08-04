import sqlite3
import os
import time

DB_PATH = 'data/trading.db'

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    
    print("Migrating minute_ohlcv time to INTEGER...")
    start = time.time()
    
    conn.execute("""
    CREATE TABLE minute_ohlcv_new (
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
    conn.execute("INSERT INTO minute_ohlcv_new SELECT ticker, date, CAST(time AS INTEGER), open, high, low, close, volume, amount FROM minute_ohlcv")
    conn.execute("DROP TABLE minute_ohlcv")
    conn.execute("ALTER TABLE minute_ohlcv_new RENAME TO minute_ohlcv")
    
    print(f"Migrated minute_ohlcv time in {time.time() - start:.2f}s")
    
    conn.commit()
    
    print("Vacuuming database...")
    start = time.time()
    conn.execute("VACUUM")
    print(f"Vacuum completed in {time.time() - start:.2f}s")
    
    conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
