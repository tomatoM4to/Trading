import os
import sqlite3
import time

DB_PATH = "data/trading.db"


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")

    print("Migrating stock_codes to WITHOUT ROWID, STRICT...")
    start = time.time()

    # Check if stock_codes exists
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_codes'"
    )
    if not cursor.fetchone():
        print("stock_codes table does not exist. Skipping.")
        return

    conn.execute("""
        CREATE TABLE stock_codes_new (
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
    conn.execute("""
        INSERT INTO stock_codes_new
        SELECT
            ticker, name, market, market_cap, total_shares, credit_able, margin_rate,
            revenue, operating_profit, net_income, roe, is_halted, is_admin_issue,
            is_overheated, is_warning
        FROM stock_codes
    """)
    conn.execute("DROP TABLE stock_codes")
    conn.execute("ALTER TABLE stock_codes_new RENAME TO stock_codes")

    print(f"Migrated stock_codes in {time.time() - start:.2f}s")

    conn.commit()
    conn.close()
    print("Migration complete!")


if __name__ == "__main__":
    migrate()
