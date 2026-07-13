import sqlite3
from typing import Any


def get_global_status_service(
    data_type: str, conn: sqlite3.Connection
) -> dict[str, Any]:
    """
    모든 종목이 최신 데이터를 가지고 있는지 파악합니다.
    """
    if data_type not in ("daily", "minute"):
        raise ValueError(f"Invalid data_type: {data_type}")

    # 전체 종목 리스트 획득
    cursor = conn.execute("SELECT ticker FROM stock_codes")
    all_tickers = [row["ticker"] for row in cursor.fetchall()]

    # OHLCV 테이블에서 각 종목별 최신 날짜 획득
    table_name = "daily_ohlcv" if data_type == "daily" else "minute_ohlcv"
    cursor = conn.execute(
        f"SELECT ticker, MAX(date) as max_date FROM {table_name} GROUP BY ticker"
    )

    ticker_max_dates = {row["ticker"]: row["max_date"] for row in cursor.fetchall()}

    if not ticker_max_dates:
        return {
            "data_type": data_type,
            "global_max_date": None,
            "up_to_date_ratio_percent": 0.0,
            "lagging_tickers_count": len(all_tickers),
            "lagging_tickers": [{"ticker": t, "last_date": None} for t in all_tickers],
        }

    global_max_date = max(ticker_max_dates.values())

    lagging_tickers = []
    for t in all_tickers:
        last_date = ticker_max_dates.get(t)
        if last_date != global_max_date:
            lagging_tickers.append({"ticker": t, "last_date": last_date})

    total_count = len(all_tickers)
    lagging_count = len(lagging_tickers)
    up_to_date_count = total_count - lagging_count
    ratio = (up_to_date_count / total_count * 100) if total_count > 0 else 0.0

    return {
        "data_type": data_type,
        "global_max_date": global_max_date,
        "up_to_date_ratio_percent": round(ratio, 2),
        "total_tickers": total_count,
        "up_to_date_tickers": up_to_date_count,
        "lagging_tickers_count": lagging_count,
        "lagging_tickers": lagging_tickers,
    }


def get_ticker_status_service(
    ticker: str, data_type: str, conn: sqlite3.Connection
) -> dict[str, Any]:
    """
    특정 종목의 ohlcv 데이터 개수와 범위(시작일, 종료일)를 반환합니다.
    """
    if data_type not in ("daily", "minute"):
        raise ValueError(f"Invalid data_type: {data_type}")

    table_name = "daily_ohlcv" if data_type == "daily" else "minute_ohlcv"

    cursor = conn.execute(
        f"SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(*) as cnt FROM {table_name} WHERE ticker = ?",
        (ticker,),
    )
    row = cursor.fetchone()

    return {
        "ticker": ticker,
        "data_type": data_type,
        "total_count": row["cnt"] or 0,
        "first_date": row["min_date"],
        "last_date": row["max_date"],
    }
