import sqlite3

from core.database import connect_sqlite
from schemas.market import (
    ChartDataPoint,
    ChartDataResponse,
    TopVolumeItem,
    TopVolumeResponse,
)


async def get_top_volume_tickers(limit: int = 30) -> TopVolumeResponse:
    """
    최근 영업일 기준으로 거래량 상위 N개의 종목을 반환합니다.
    """
    conn = connect_sqlite()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 가장 최신 영업일 조회
        cursor.execute("SELECT MAX(date) as max_date FROM daily_ohlcv")
        row = cursor.fetchone()
        latest_date = row["max_date"] if row and row["max_date"] else None

        if not latest_date:
            return TopVolumeResponse(date="N/A", items=[])

        # 최신 영업일의 거래량 상위 N개 종목과 이름 조회
        query = """
            SELECT d.ticker, s.name, d.volume
            FROM daily_ohlcv d
            JOIN stock_codes s ON d.ticker = s.ticker
            WHERE d.date = ?
            ORDER BY d.volume DESC
            LIMIT ?
        """
        cursor.execute(query, (latest_date, limit))
        rows = cursor.fetchall()

        items = [
            TopVolumeItem(ticker=r["ticker"], name=r["name"], volume=r["volume"])
            for r in rows
        ]

        return TopVolumeResponse(date=latest_date, items=items)

    finally:
        cursor.close()
        conn.close()


async def get_chart_data(
    ticker: str, days: int = 3, timeframe: str = "minute"
) -> ChartDataResponse:
    """
    특정 종목의 다중 주기 이평선이 포함된 데이터를 반환합니다.
    timeframe: 'minute' (분봉) 또는 'daily' (일봉)
    """
    conn = connect_sqlite()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 1. 종목 이름 조회
        cursor.execute("SELECT name FROM stock_codes WHERE ticker = ?", (ticker,))
        row = cursor.fetchone()
        name = row["name"] if row else "Unknown"

        data_points = []

        if timeframe == "daily":
            # 일봉 전체 데이터 쿼리
            query = """
                SELECT 
                    date,
                    '153000' as time,
                    open, high, low, close, volume,
                    close as ma_daily_1,
                    AVG(close) OVER (ORDER BY date ASC ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) as ma_daily_5,
                    AVG(close) OVER (ORDER BY date ASC ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as ma_daily_20,
                    AVG(close) OVER (ORDER BY date ASC ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) as ma_daily_60,
                    AVG(close) OVER (ORDER BY date ASC ROWS BETWEEN 119 PRECEDING AND CURRENT ROW) as ma_daily_120
                FROM daily_ohlcv
                WHERE ticker = ?
                ORDER BY date ASC
            """
            cursor.execute(query, (ticker,))
            rows = cursor.fetchall()

            for r in rows:
                date_str = r["date"]
                time_str = r["time"]
                formatted_time = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"

                data_points.append(
                    ChartDataPoint(
                        time=formatted_time,
                        open=r["open"],
                        high=r["high"],
                        low=r["low"],
                        close=r["close"],
                        volume=r["volume"],
                        ma1=None,
                        ma5=None,
                        ma10=None,
                        ma20=None,
                        ma60=None,
                        ma120=None,
                        ma_daily_1=r["ma_daily_1"],
                        ma_daily_5=r["ma_daily_5"],
                        ma_daily_20=r["ma_daily_20"],
                        ma_daily_60=r["ma_daily_60"],
                        ma_daily_120=r["ma_daily_120"],
                    )
                )

        else:
            # 2. 최근 N 영업일 기준일자 구하기
            cursor.execute(
                "SELECT date FROM daily_ohlcv WHERE ticker = ? ORDER BY date DESC LIMIT 1 OFFSET ?",
                (ticker, max(0, days - 1)),
            )
            date_row = cursor.fetchone()
            start_date = date_row["date"] if date_row else "00000000"

            # 3. 통합 차트 쿼리 (Daily CTE + Minute CTE)
            query = """
                WITH daily_ma AS (
                    SELECT 
                        date,
                        close as ma_daily_1,
                        AVG(close) OVER (ORDER BY date ASC ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) as ma_daily_5,
                        AVG(close) OVER (ORDER BY date ASC ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as ma_daily_20,
                        AVG(close) OVER (ORDER BY date ASC ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) as ma_daily_60,
                        AVG(close) OVER (ORDER BY date ASC ROWS BETWEEN 119 PRECEDING AND CURRENT ROW) as ma_daily_120
                    FROM daily_ohlcv
                    WHERE ticker = ?
                ),
                minute_ma AS (
                    SELECT
                        date,
                        time,
                        open, high, low, close, volume,
                        AVG(close) OVER (ORDER BY date ASC, time ASC ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) as ma5,
                        AVG(close) OVER (ORDER BY date ASC, time ASC ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) as ma10,
                        AVG(close) OVER (ORDER BY date ASC, time ASC ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as ma20,
                        AVG(close) OVER (ORDER BY date ASC, time ASC ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) as ma60,
                        AVG(close) OVER (ORDER BY date ASC, time ASC ROWS BETWEEN 119 PRECEDING AND CURRENT ROW) as ma120
                    FROM minute_ohlcv
                    WHERE ticker = ?
                )
                SELECT 
                    m.date, m.time, m.open, m.high, m.low, m.close, m.volume,
                    m.ma5, m.ma10, m.ma20, m.ma60, m.ma120,
                    d.ma_daily_1, d.ma_daily_5, d.ma_daily_20, d.ma_daily_60, d.ma_daily_120
                FROM minute_ma m
                LEFT JOIN daily_ma d ON m.date = d.date
                WHERE m.date >= ?
                ORDER BY m.date ASC, m.time ASC
            """
            cursor.execute(query, (ticker, ticker, start_date))
            rows = cursor.fetchall()

            for r in rows:
                date_str = r["date"]
                time_str = r["time"]
                formatted_time = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"

                data_points.append(
                    ChartDataPoint(
                        time=formatted_time,
                        open=r["open"],
                        high=r["high"],
                        low=r["low"],
                        close=r["close"],
                        volume=r["volume"],
                        ma1=r["close"],  # 1분 이평선은 현재가(종가) 자체
                        ma5=r["ma5"],
                        ma10=r["ma10"],
                        ma20=r["ma20"],
                        ma60=r["ma60"],
                        ma120=r["ma120"],
                        ma_daily_1=r["ma_daily_1"],
                        ma_daily_5=r["ma_daily_5"],
                        ma_daily_20=r["ma_daily_20"],
                        ma_daily_60=r["ma_daily_60"],
                        ma_daily_120=r["ma_daily_120"],
                    )
                )

        return ChartDataResponse(ticker=ticker, name=name, data=data_points)

    finally:
        cursor.close()
        conn.close()
