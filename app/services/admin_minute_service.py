from fastapi import HTTPException

async def verify_minute_integrity_service(sample_size: int = 10, market: str = "KOSPI"):
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
