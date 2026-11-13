import argparse
import asyncio
import importlib
import logging
import re
import sys
from datetime import datetime
from pathlib import Path


async def run(ticker):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    logging.disable(logging.CRITICAL)
    stop_q_worker = None
    try:
        importlib.import_module("core.logging")
        from core import kis_auth
        from core.kis_fetch import stop_q_worker
        from tasks.daily_ohlcv_scheduler import fetch_and_save_ohlcv

        await asyncio.to_thread(kis_auth.auth, force=False)
        if kis_auth.get_kis_env() is None:
            print("Authentication failed")
            return 1
        rows = await fetch_and_save_ohlcv(ticker, datetime.now(), 7, priority=7)
        if not rows:
            print("No candles returned; live validation incomplete")
            return 1
        fields = (
            "stck_bsop_date",
            "stck_oprc",
            "stck_hgpr",
            "stck_lwpr",
            "stck_clpr",
            "acml_vol",
            "acml_tr_pbmn",
        )
        for row in rows:
            for field in fields:
                int(row[field])
        print(
            f"Live read-only schema probe: {len(rows)} candles, 1 queued data request"
        )
        return 0
    except Exception as error:
        print(f"Live probe failed: {type(error).__name__}")
        return 1
    finally:
        if stop_q_worker is not None:
            await stop_q_worker()


def main():
    parser = argparse.ArgumentParser(
        description="Optional live probe: at most 1 OAuth issuance and 1 queued read-only daily request; token cache may be updated"
    )
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--ticker", default="005930")
    args = parser.parse_args()
    if not args.allow_live:
        parser.error(
            "Explicit --allow-live is required before importing KIS configuration"
        )
    if not re.fullmatch(r"\d{6}", args.ticker):
        parser.error("ticker must contain exactly six digits")
    return asyncio.run(run(args.ticker))


if __name__ == "__main__":
    raise SystemExit(main())
