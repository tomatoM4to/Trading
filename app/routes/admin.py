from fastapi import APIRouter, HTTPException

router = APIRouter()
daily_router = APIRouter(prefix="/admin/daily", tags=["Admin (Daily OHLCV)"])
minute_router = APIRouter(prefix="/admin/minute", tags=["Admin (Minute OHLCV)"])


@daily_router.get("/check")
def check_daily_ohlcv(market: str = "KOSPI"):
    """
    적재된 일봉 데이터의 정합성과 과거 데이터 충분성을 검증합니다.
    """
    from core.database import connect_sqlite

    conn = connect_sqlite()
    try:
        cursor = conn.cursor()

        # 1. 마스터 테이블(stock_codes)의 전체 종목 수 (거래정지 등이 이미 제외된 순수 매매 가능 종목)
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
        distribution = [dict(row) for row in cursor.fetchall()]

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

        if distribution and target_total_tickers > 0:
            most_recent_count = distribution[0]["ticker_count"]

            # 일봉 스케줄러의 특징 및 종목 필터링(거래정지 제외) 특성상 최신 날짜 보유 비율 100%를 요구
            is_up_to_date = most_recent_count == target_total_tickers

            # 과거 데이터는 신규 상장 종목이 있으므로 90% 이상이면 정상으로 판별
            is_deep_enough = deep_history_count >= target_total_tickers * 0.9

            if is_up_to_date and is_deep_enough:
                status = "Healthy (최신화 100% 완료 및 과거 데이터 충분)"
            elif not is_up_to_date:
                status = f"Needs Check (최신 데이터 누락: {most_recent_count}/{target_total_tickers})"
            else:
                status = "Needs Check (과거 데이터 부족 종목 다수)"

        return {
            "status": status,
            "target_total_tickers": target_total_tickers,
            "total_saved_rows": total_rows,
            "up_to_date_integrity": {
                "latest_date": distribution[0]["last_date"] if distribution else None,
                "tickers_with_latest_date": distribution[0]["ticker_count"]
                if distribution
                else 0,
                "is_100_percent": is_up_to_date,
            },
            "historical_depth_integrity": {
                "tickers_with_400_plus_days": deep_history_count,
                "percentage": round(
                    (deep_history_count / target_total_tickers) * 100, 1
                )
                if target_total_tickers > 0
                else 0,
                "is_healthy": is_deep_enough,
            },
            "latest_date_distribution": distribution,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB Query Error: {e}") from e
    finally:
        conn.close()


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


@daily_router.get("/verify")
async def verify_daily_integrity(sample_size: int = 10, market: str = "KOSPI"):
    """
    무작위 종목을 추출하여, KIS API의 과거 일봉 데이터(최소 5일 전)와
    현재 DB(daily_ohlcv)에 적재된 데이터가 정확히 일치하는지 무결성을 검증합니다.
    """
    import random
    from datetime import datetime, timedelta

    from core.database import connect_sqlite
    from tasks.daily_ohlcv_scheduler import fetch_and_save_ohlcv

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

            # 2. 5일 ~ 300일 전 사이의 무작위 종료일 설정 (너무 최신 데이터 배제)
            random_days_ago = random.randint(5, 300)
            end_date = datetime.now() - timedelta(days=random_days_ago)

            # 3. KIS API 호출 (end_date로부터 과거 100영업일치 캔들 요청)
            try:
                # days_to_subtract를 150으로 주어 주말/휴일 감안하더라도 KIS API 최대치인 100개를 받아옴
                api_data = await fetch_and_save_ohlcv(
                    ticker, end_date, days_to_subtract=150, priority=2
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

            if not api_data:
                results.append(
                    {"ticker": ticker, "name": t_info["name"], "status": "NO_API_DATA"}
                )
                continue

            # API 데이터 중 정상 일자만 필터링
            valid_api_items = [item for item in api_data if item.stck_bsop_date]
            if not valid_api_items:
                results.append(
                    {
                        "ticker": ticker,
                        "name": t_info["name"],
                        "status": "NO_VALID_API_DATA",
                    }
                )
                continue

            # DB 검증을 위해 날짜 리스트 추출
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
                    if (
                        len(mismatch_details) < 5
                    ):  # 각 종목당 최대 5개까지만 상세 리포트
                        mismatch_details.append(
                            {
                                "date": date_val,
                                "api": {
                                    "open": api_open,
                                    "high": api_high,
                                    "low": api_low,
                                    "close": api_close,
                                    "vol": api_volume,
                                    "amt": api_amount,
                                },
                                "db": {
                                    "open": db_row["open"],
                                    "high": db_row["high"],
                                    "low": db_row["low"],
                                    "close": db_row["close"],
                                    "vol": db_row["volume"],
                                    "amt": db_row["amount"],
                                },
                            }
                        )

            total_candles_checked += len(valid_api_items)
            total_mismatches += mismatch_count
            total_missing += missing_in_db_count

            status = (
                "PASS" if mismatch_count == 0 and missing_in_db_count == 0 else "FAIL"
            )

            results.append(
                {
                    "ticker": ticker,
                    "name": t_info["name"],
                    "target_end_date": end_date.strftime("%Y%m%d"),
                    "candles_checked": len(valid_api_items),
                    "matches": match_count,
                    "mismatches": mismatch_count,
                    "missing_in_db": missing_in_db_count,
                    "missing_dates": missing_dates,
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
            status_code=500, detail=f"Daily Verification Error: {e}"
        ) from e
    finally:
        conn.close()


router.include_router(daily_router)
router.include_router(minute_router)
