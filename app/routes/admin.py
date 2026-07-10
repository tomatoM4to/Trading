from fastapi import APIRouter, HTTPException
from schemas.admin import DailyCheckResponse, DailyVerifyResponse
from services.admin_daily_service import (
    check_daily_ohlcv_service,
    verify_daily_integrity_service,
)

router = APIRouter()
daily_router = APIRouter(prefix="/admin/daily", tags=["Admin (Daily OHLCV)"])
minute_router = APIRouter(prefix="/admin/minute", tags=["Admin (Minute OHLCV)"])


@daily_router.get("/check", response_model=DailyCheckResponse)
def check_daily_ohlcv(market: str = "KOSPI"):
    """
    적재된 일봉 데이터의 정합성과 과거 데이터 충분성을 검증합니다.
    """
    return check_daily_ohlcv_service(market)

@daily_router.get("/verify", response_model=DailyVerifyResponse)
async def verify_daily_integrity(sample_size: int = 10, market: str = "KOSPI"):
    """
    무작위 종목을 추출하여, KIS API의 과거 일봉 데이터(최소 5일 전)와
    현재 DB(daily_ohlcv)에 적재된 데이터가 정확히 일치하는지 무결성을 검증합니다.
    """
    return await verify_daily_integrity_service(sample_size, market)


@minute_router.get("/check")
def check_minute_ohlcv(market: str = "KOSPI"):
    """
    적재된 분봉 데이터의 정합성을 검증합니다.
    종목별 가장 최신 분봉 시간(date + time)의 분포를 확인하여
    대부분의 종목이 최신 시간까지 정상적으로 적재되었는지 판별합니다.
    """
    from core.database import connect_sqlite

    conn = connect_sqlite()
    try:
        cursor = conn.cursor()

        # 1. 종목별 최신 날짜시간(MAX(date || time))을 구하고 분포(Count)를 계산
        query = """
            SELECT
                last_datetime,
                COUNT(*) as ticker_count
            FROM (
                SELECT m.ticker, MAX(m.date || ' ' || m.time) as last_datetime
                FROM minute_ohlcv m
                JOIN stock_codes s ON m.ticker = s.ticker
                WHERE s.market = ?
                GROUP BY m.ticker
            )
            GROUP BY last_datetime
            ORDER BY last_datetime DESC
        """
        cursor.execute(query, (market,))
        distribution = [dict(row) for row in cursor.fetchall()]

        # 2. 적재된 고유 종목 수 및 전체 캔들 수 확인
        cursor.execute(
            """
            SELECT COUNT(DISTINCT m.ticker)
            FROM minute_ohlcv m
            JOIN stock_codes s ON m.ticker = s.ticker
            WHERE s.market = ?
        """,
            (market,),
        )
        total_tickers = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM minute_ohlcv m
            JOIN stock_codes s ON m.ticker = s.ticker
            WHERE s.market = ?
        """,
            (market,),
        )
        total_rows = cursor.fetchone()[0]

        status = "No Data"
        if distribution and total_tickers > 0:
            # 분봉은 스케줄러가 도는 35분 동안 수집 시점이 계속 변하고,
            # 거래량이 없는 소외주는 최신 분봉이 10분 전일 수도 있어서 '정확히 같은 분(Minute)'으로 80%가 뭉치는 것은 불가능합니다.
            # 따라서 최신 날짜(YYYYMMDD)가 같은 종목들의 비율을 합산하여 정합성을 평가합니다.
            most_recent_date = distribution[0]["last_datetime"][:8]  # '20260707'

            same_date_count = 0
            for row in distribution:
                if row["last_datetime"].startswith(most_recent_date):
                    same_date_count += row["ticker_count"]

            if same_date_count >= total_tickers * 0.7:
                status = "Healthy (정상 적재 완료: 분봉 시간은 종목별 거래량/수집 시간에 따라 자연스럽게 분산됨)"
            else:
                status = "Needs Check (최신 날짜 기준 업데이트 누락 종목 다수)"

        return {
            "status": status,
            "total_saved_tickers": total_tickers,
            "total_saved_rows": total_rows,
            "average_minutes_per_ticker": round(total_rows / total_tickers, 1)
            if total_tickers > 0
            else 0,
            "latest_time_distribution": distribution[:10],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB Query Error: {e}") from e
    finally:
        conn.close()


@minute_router.get("/verify")
async def verify_minute_integrity(sample_size: int = 10, market: str = "KOSPI"):
    """
    무작위 종목을 추출하여, DB에 저장된 가장 최신 시점을 기준으로 KIS API를 다시 호출해
    현재 DB(minute_ohlcv)에 적재된 데이터(시가/고가/저가/종가/거래량)가 100% 일치하는지 정합성을 검증합니다.
    """
    from core.database import connect_sqlite
    from tasks.minute_ohlcv_scheduler import fetch_minute_data

    conn = connect_sqlite()
    try:
        cursor = conn.cursor()

        # 1. 무작위 종목 추출
        cursor.execute(
            "SELECT ticker, name FROM stock_codes WHERE market = ? ORDER BY RANDOM() LIMIT ?",
            (market, sample_size),
        )
        tickers = [dict(row) for row in cursor.fetchall()]

        if not tickers:
            raise HTTPException(
                status_code=404, detail=f"No tickers found in stock_codes for {market}."
            )

        results = []
        total_candles_checked = 0
        total_mismatches = 0
        total_missing = 0

        for t_info in tickers:
            ticker = t_info["ticker"]

            # 2. DB에서 해당 종목의 가장 최신 날짜/시간 조회 (스케줄러 딜레이로 인한 실시간 노이즈 방지)
            cursor.execute(
                "SELECT date, time FROM minute_ohlcv WHERE ticker = ? ORDER BY date DESC, time DESC LIMIT 1",
                (ticker,),
            )
            latest_row = cursor.fetchone()
            if not latest_row:
                results.append(
                    {"ticker": ticker, "name": t_info["name"], "status": "NO_DB_DATA"}
                )
                continue

            target_date = latest_row["date"]
            target_time = latest_row["time"]

            # 3. KIS API 호출 (DB의 최신 시점부터 과거 120개) - VIP 우선순위(2) 적용
            try:
                api_df = await fetch_minute_data(
                    ticker, target_date, target_time, priority=2
                )
            except Exception as e:
                results.append(
                    {
                        "ticker": ticker,
                        "name": t_info["name"],
                        "status": "API_ERROR",
                        "detail": str(e),
                    }
                )
                continue

            if api_df.empty:
                results.append(
                    {"ticker": ticker, "name": t_info["name"], "status": "NO_API_DATA"}
                )
                continue

            # 4. DB 일괄 조회를 위한 조건문 생성
            conds = []
            params = [ticker]
            for _, row in api_df.iterrows():
                conds.append("(date = ? AND time = ?)")
                params.extend([row.get("stck_bsop_date"), row.get("stck_cntg_hour")])

            query = f"SELECT date, time, open, high, low, close, volume FROM minute_ohlcv WHERE ticker = ? AND ({' OR '.join(conds)})"
            cursor.execute(query, params)

            # (date, time)을 키로 하는 딕셔너리로 변환하여 고속 탐색
            db_rows = {
                (row["date"], row["time"]): dict(row) for row in cursor.fetchall()
            }

            # 5. 데이터 1:1 검증
            match_count = 0
            mismatch_count = 0
            missing_in_db_count = 0
            mismatch_details = []

            for _, row in api_df.iterrows():
                date_val = row.get("stck_bsop_date")
                time_val = row.get("stck_cntg_hour")

                api_open = int(row.get("stck_oprc", 0))
                api_high = int(row.get("stck_hgpr", 0))
                api_low = int(row.get("stck_lwpr", 0))
                api_close = int(row.get("stck_prpr", 0))
                api_volume = int(row.get("cntg_vol", 0))

                db_row = db_rows.get((date_val, time_val))

                if not db_row:
                    missing_in_db_count += 1
                    continue

                if (
                    api_open == db_row["open"]
                    and api_high == db_row["high"]
                    and api_low == db_row["low"]
                    and api_close == db_row["close"]
                    and api_volume == db_row["volume"]
                ):
                    match_count += 1
                else:
                    mismatch_count += 1
                    if len(mismatch_details) < 5:
                        mismatch_details.append(
                            {
                                "date": date_val,
                                "time": time_val,
                                "api": {
                                    "open": api_open,
                                    "high": api_high,
                                    "low": api_low,
                                    "close": api_close,
                                    "vol": api_volume,
                                },
                                "db": {
                                    "open": db_row["open"],
                                    "high": db_row["high"],
                                    "low": db_row["low"],
                                    "close": db_row["close"],
                                    "vol": db_row["volume"],
                                },
                            }
                        )

            total_candles_checked += len(api_df)
            total_mismatches += mismatch_count
            total_missing += missing_in_db_count

            status = (
                "PASS" if mismatch_count == 0 and missing_in_db_count == 0 else "FAIL"
            )

            results.append(
                {
                    "ticker": ticker,
                    "name": t_info["name"],
                    "target_datetime": f"{target_date} {target_time}",
                    "candles_checked": len(api_df),
                    "matches": match_count,
                    "mismatches": mismatch_count,
                    "missing_in_db": missing_in_db_count,
                    "status": status,
                    "mismatch_sample": mismatch_details,
                }
            )

        overall_status = (
            "Healthy (100% Match)"
            if total_mismatches == 0 and total_missing == 0
            else "Needs Check (Mismatches Found)"
        )
        return {
            "overall_status": overall_status,
            "summary": {
                "tickers_sampled": len(tickers),
                "total_candles_checked": total_candles_checked,
                "total_mismatches": total_mismatches,
                "total_missing_in_db": total_missing,
                "accuracy_rate": round(
                    (
                        (total_candles_checked - total_mismatches - total_missing)
                        / total_candles_checked
                        * 100
                    ),
                    2,
                )
                if total_candles_checked > 0
                else 0,
            },
            "details": results,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Minute Verification Error: {e}"
        ) from e
    finally:
        conn.close()


router.include_router(daily_router)
router.include_router(minute_router)
