import random
from datetime import datetime, timedelta

from core.database import connect_sqlite
from fastapi import HTTPException
from schemas.admin import (
    CandleData,
    DailyCheckResponse,
    DailyVerifyResponse,
    DateDistribution,
    HistoricalDepthIntegrity,
    MismatchSample,
    UpToDateIntegrity,
    VerifyDetail,
    VerifySummary,
)
from tasks.daily_ohlcv_scheduler import fetch_and_save_ohlcv


def check_daily_ohlcv_service(market: str = "KOSPI") -> DailyCheckResponse:
    conn = connect_sqlite()
    try:
        cursor = conn.cursor()

        # 1. 마스터 테이블(stock_codes)의 전체 종목 수
        cursor.execute("SELECT COUNT(*) FROM stock_codes WHERE market = ?", (market,))
        target_total_tickers = cursor.fetchone()[0]

        # 2. 일봉 테이블에 적재된 최신 날짜 분포
        query_latest = """
            SELECT
                last_date,
                COUNT(*) as ticker_count
            FROM (
                SELECT d.ticker, MAX(d.date) as last_date
                FROM daily_ohlcv d
                JOIN stock_codes s ON d.ticker = s.ticker
                WHERE s.market = ?
                GROUP BY d.ticker
            )
            GROUP BY last_date
            ORDER BY last_date DESC
            LIMIT 5
        """
        cursor.execute(query_latest, (market,))
        distribution_raw = [dict(row) for row in cursor.fetchall()]

        # 3. 과거 데이터 충분성 (400일 이상 데이터가 적재된 종목 수)
        query_depth = """
            SELECT COUNT(*) FROM (
                SELECT d.ticker
                FROM daily_ohlcv d
                JOIN stock_codes s ON d.ticker = s.ticker
                WHERE s.market = ?
                GROUP BY d.ticker
                HAVING COUNT(*) >= 400
            )
        """
        cursor.execute(query_depth, (market,))
        deep_history_count = cursor.fetchone()[0]

        # 4. 전체 캔들 수
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM daily_ohlcv d
            JOIN stock_codes s ON d.ticker = s.ticker
            WHERE s.market = ?
        """,
            (market,),
        )
        total_rows = cursor.fetchone()[0]

        status = "No Data"
        is_up_to_date = False
        is_deep_enough = False

        if distribution_raw and target_total_tickers > 0:
            most_recent_count = distribution_raw[0]["ticker_count"]

            is_up_to_date = most_recent_count == target_total_tickers
            is_deep_enough = deep_history_count >= target_total_tickers * 0.9

            if is_up_to_date and is_deep_enough:
                status = "Healthy (최신화 100% 완료 및 과거 데이터 충분)"
            elif not is_up_to_date:
                status = f"Needs Check (최신 데이터 누락: {most_recent_count}/{target_total_tickers})"
            else:
                status = "Needs Check (과거 데이터 부족 종목 다수)"

        distribution = [
            DateDistribution(last_date=d["last_date"], ticker_count=d["ticker_count"])
            for d in distribution_raw
        ]

        up_to_date = UpToDateIntegrity(
            latest_date=distribution_raw[0]["last_date"] if distribution_raw else None,
            tickers_with_latest_date=distribution_raw[0]["ticker_count"]
            if distribution_raw
            else 0,
            is_100_percent=is_up_to_date,
        )

        hist_depth = HistoricalDepthIntegrity(
            tickers_with_400_plus_days=deep_history_count,
            percentage=round((deep_history_count / target_total_tickers) * 100, 1)
            if target_total_tickers > 0
            else 0.0,
            is_healthy=is_deep_enough,
        )

        return DailyCheckResponse(
            status=status,
            target_total_tickers=target_total_tickers,
            total_saved_rows=total_rows,
            up_to_date_integrity=up_to_date,
            historical_depth_integrity=hist_depth,
            latest_date_distribution=distribution,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB Query Error: {e}") from e
    finally:
        conn.close()


async def verify_daily_integrity_service(
    sample_size: int = 10, market: str = "KOSPI"
) -> DailyVerifyResponse:
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

            # 2. 5일 ~ 300일 전 사이의 무작위 종료일 설정
            random_days_ago = random.randint(5, 300)
            end_date = datetime.now() - timedelta(days=random_days_ago)

            # 3. KIS API 호출
            try:
                api_data = await fetch_and_save_ohlcv(
                    ticker, end_date, days_to_subtract=150, priority=2
                )
            except Exception:
                results.append(
                    VerifyDetail(
                        ticker=ticker,
                        name=t_info["name"],
                        target_end_date=end_date.strftime("%Y%m%d"),
                        candles_checked=0,
                        matches=0,
                        mismatches=0,
                        missing_in_db=0,
                        missing_dates=[],
                        status="API_ERROR",
                        mismatch_sample=[],
                    )
                )
                continue

            if not api_data:
                results.append(
                    VerifyDetail(
                        ticker=ticker,
                        name=t_info["name"],
                        target_end_date=end_date.strftime("%Y%m%d"),
                        candles_checked=0,
                        matches=0,
                        mismatches=0,
                        missing_in_db=0,
                        missing_dates=[],
                        status="NO_API_DATA",
                        mismatch_sample=[],
                    )
                )
                continue

            valid_api_items = [item for item in api_data if item.stck_bsop_date]
            if not valid_api_items:
                results.append(
                    VerifyDetail(
                        ticker=ticker,
                        name=t_info["name"],
                        target_end_date=end_date.strftime("%Y%m%d"),
                        candles_checked=0,
                        matches=0,
                        mismatches=0,
                        missing_in_db=0,
                        missing_dates=[],
                        status="NO_VALID_API_DATA",
                        mismatch_sample=[],
                    )
                )
                continue

            date_list = [item.stck_bsop_date for item in valid_api_items]
            placeholders = ",".join(["?"] * len(date_list))

            # 4. DB 데이터 조회
            query = f"SELECT date, open, high, low, close, volume, amount FROM daily_ohlcv WHERE ticker = ? AND date IN ({placeholders})"
            cursor.execute(query, [ticker] + date_list)
            db_rows = {row["date"]: dict(row) for row in cursor.fetchall()}

            # 5. 데이터 비교
            match_count = 0
            mismatch_count = 0
            missing_in_db_count = 0
            mismatch_details = []
            missing_dates = []

            for item in valid_api_items:
                date_val = item.stck_bsop_date
                api_open = int(item.stck_oprc)
                api_high = int(item.stck_hgpr)
                api_low = int(item.stck_lwpr)
                api_close = int(item.stck_clpr)
                api_volume = int(item.acml_vol)
                api_amount = int(item.acml_tr_pbmn)

                db_row = db_rows.get(date_val)
                if not db_row:
                    missing_in_db_count += 1
                    missing_dates.append(date_val)
                    continue

                if (
                    api_open == db_row["open"]
                    and api_high == db_row["high"]
                    and api_low == db_row["low"]
                    and api_close == db_row["close"]
                    and api_volume == db_row["volume"]
                    and api_amount == db_row["amount"]
                ):
                    match_count += 1
                else:
                    mismatch_count += 1
                    if len(mismatch_details) < 5:
                        mismatch_details.append(
                            MismatchSample(
                                date=date_val,
                                api=CandleData(
                                    open=api_open,
                                    high=api_high,
                                    low=api_low,
                                    close=api_close,
                                    vol=api_volume,
                                    amt=api_amount,
                                ),
                                db=CandleData(
                                    open=db_row["open"],
                                    high=db_row["high"],
                                    low=db_row["low"],
                                    close=db_row["close"],
                                    vol=db_row["volume"],
                                    amt=db_row["amount"],
                                ),
                            )
                        )

            total_candles_checked += len(valid_api_items)
            total_mismatches += mismatch_count
            total_missing += missing_in_db_count

            status = (
                "PASS" if mismatch_count == 0 and missing_in_db_count == 0 else "FAIL"
            )

            results.append(
                VerifyDetail(
                    ticker=ticker,
                    name=t_info["name"],
                    target_end_date=end_date.strftime("%Y%m%d"),
                    candles_checked=len(valid_api_items),
                    matches=match_count,
                    mismatches=mismatch_count,
                    missing_in_db=missing_in_db_count,
                    missing_dates=missing_dates,
                    status=status,
                    mismatch_sample=mismatch_details,
                )
            )

        overall_status = (
            "Healthy (100% Match)"
            if total_mismatches == 0 and total_missing == 0
            else "Needs Check (Mismatches Found)"
        )

        accuracy_rate = 0.0
        if total_candles_checked > 0:
            accuracy_rate = round(
                (
                    (total_candles_checked - total_mismatches - total_missing)
                    / total_candles_checked
                )
                * 100,
                2,
            )

        summary = VerifySummary(
            tickers_sampled=len(tickers),
            total_candles_checked=total_candles_checked,
            total_mismatches=total_mismatches,
            total_missing_in_db=total_missing,
            accuracy_rate=accuracy_rate,
        )

        return DailyVerifyResponse(
            overall_status=overall_status, summary=summary, details=results
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Daily Verification Error: {e}"
        ) from e
    finally:
        conn.close()
