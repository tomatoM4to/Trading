import sqlite3
from pathlib import Path

db_path = Path("data/trading.db").resolve()
print(f"Connecting to {db_path}...")

conn = sqlite3.connect(db_path)
print("1. Running WAL Checkpoint (TRUNCATE)...")
res = conn.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchall()
print(f"Checkpoint result: {res}")

print("2. Running VACUUM to optimize space...")
conn.execute("VACUUM;")
print("VACUUM finished.")

conn.close()
print("Done. You can now safely copy trading.db.")
