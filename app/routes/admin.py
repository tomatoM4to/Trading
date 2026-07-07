from fastapi import APIRouter, HTTPException
from tasks.daily_ohlcv_scheduler import start_scheduler_task, stop_scheduler_task
from tasks.minute_ohlcv_scheduler import start_minute_scheduler_task, stop_minute_scheduler_task

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/start-daily-ohlcv")
async def trigger_daily_ohlcv(market: str = "KOSPI"):
    """
    KOSPI 또는 KOSDAQ 종목들의 1일봉(OHLCV) 데이터를 200일 치 수집하는 백그라운드 태스크를 강제 시작합니다.
    """
    started = await start_scheduler_task(market)
    if started:
        return {"message": f"Successfully started daily OHLCV scheduler for {market}."}
    else:
        raise HTTPException(status_code=400, detail="Scheduler is already running.")

@router.post("/stop-daily-ohlcv")
async def cancel_daily_ohlcv():
    """
    현재 구동 중인 1일봉 데이터 수집 스케줄러 태스크를 강제로 중지합니다.
    """
    stopped = await stop_scheduler_task()
    if stopped:
        return {"message": "Successfully stopped the running scheduler."}
    else:
        return {"message": "No running scheduler found to stop."}

@router.post("/start-minute-ohlcv")
async def trigger_minute_ohlcv(market: str = "KOSPI"):
    """
    KOSPI 또는 KOSDAQ 종목들의 분봉(OHLCV) 데이터를 수집하는 백그라운드 태스크를 강제 시작합니다.
    """
    started = await start_minute_scheduler_task(market)
    if started:
        return {"message": f"Successfully started minute OHLCV scheduler for {market}."}
    else:
        raise HTTPException(status_code=400, detail="Minute scheduler is already running.")

@router.post("/stop-minute-ohlcv")
async def cancel_minute_ohlcv():
    """
    현재 구동 중인 분봉 데이터 수집 스케줄러 태스크를 강제로 중지합니다.
    """
    stopped = await stop_minute_scheduler_task()
    if stopped:
        return {"message": "Successfully stopped the running minute scheduler."}
    else:
        return {"message": "No running minute scheduler found to stop."}

@router.get("/check-daily-ohlcv")
def check_daily_ohlcv():
    """
    적재된 일봉 데이터의 정합성을 검증합니다.
    오늘 날짜와 무관하게(주말/공휴일 대응), 종목별 가장 최신 거래일자의 분포를 확인하여
    대부분의 종목이 동일한 최신 날짜를 공유하고 있는지(정상 적재) 판별합니다.
    """
    from core.database import connect_sqlite

    conn = connect_sqlite()
    try:
        cursor = conn.cursor()

        # 1. 종목별 최신 날짜(MAX(date))를 구하고, 날짜별 종목 분포(Count)를 계산
        query = """
            SELECT
                last_date,
                COUNT(*) as ticker_count
            FROM (
                SELECT ticker, MAX(date) as last_date
                FROM daily_ohlcv
                GROUP BY ticker
            )
            GROUP BY last_date
            ORDER BY last_date DESC
            LIMIT 5
        """
        cursor.execute(query)
        distribution = [dict(row) for row in cursor.fetchall()]

        # 2. 적재된 고유 종목 수 및 전체 캔들(Row) 수 확인
        cursor.execute("SELECT COUNT(DISTINCT ticker) FROM daily_ohlcv")
        total_tickers = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM daily_ohlcv")
        total_rows = cursor.fetchone()[0]

        # 3. 최신 날짜를 가진 종목이 전체의 80% 이상이면 정상(Healthy)으로 판별
        status = "No Data"
        if distribution and total_tickers > 0:
            most_recent_count = distribution[0]['ticker_count']
            if most_recent_count >= total_tickers * 0.8:
                status = "Healthy (정상 적재 완료)"
            else:
                status = "Needs Check (업데이트 누락 종목 다수)"

        return {
            "status": status,
            "total_saved_tickers": total_tickers,
            "total_saved_rows": total_rows,
            "average_days_per_ticker": round(total_rows / total_tickers, 1) if total_tickers > 0 else 0,
            "latest_date_distribution": distribution
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB Query Error: {e}")
    finally:
        conn.close()

@router.get("/check-minute-ohlcv")
def check_minute_ohlcv():
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
                SELECT ticker, MAX(date || ' ' || time) as last_datetime
                FROM minute_ohlcv
                GROUP BY ticker
            )
            GROUP BY last_datetime
            ORDER BY last_datetime DESC
        """
        cursor.execute(query)
        distribution = [dict(row) for row in cursor.fetchall()]

        # 2. 적재된 고유 종목 수 및 전체 캔들 수 확인
        cursor.execute("SELECT COUNT(DISTINCT ticker) FROM minute_ohlcv")
        total_tickers = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM minute_ohlcv")
        total_rows = cursor.fetchone()[0]

        status = "No Data"
        if distribution and total_tickers > 0:
            # 분봉은 스케줄러가 도는 35분 동안 수집 시점이 계속 변하고, 
            # 거래량이 없는 소외주는 최신 분봉이 10분 전일 수도 있어서 '정확히 같은 분(Minute)'으로 80%가 뭉치는 것은 불가능합니다.
            # 따라서 최신 날짜(YYYYMMDD)가 같은 종목들의 비율을 합산하여 정합성을 평가합니다.
            most_recent_date = distribution[0]['last_datetime'][:8]  # '20260707'
            
            same_date_count = 0
            for row in distribution:
                if row['last_datetime'].startswith(most_recent_date):
                    same_date_count += row['ticker_count']
                    
            if same_date_count >= total_tickers * 0.7:
                status = "Healthy (정상 적재 완료: 분봉 시간은 종목별 거래량/수집 시간에 따라 자연스럽게 분산됨)"
            else:
                status = "Needs Check (최신 날짜 기준 업데이트 누락 종목 다수)"

        return {
            "status": status,
            "total_saved_tickers": total_tickers,
            "total_saved_rows": total_rows,
            "average_minutes_per_ticker": round(total_rows / total_tickers, 1) if total_tickers > 0 else 0,
            "latest_time_distribution": distribution[:10]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB Query Error: {e}")
    finally:
        conn.close()

@router.get("/verify-minute-integrity")
async def verify_minute_integrity(ticker: str = None):
    """
    KIS API에서 실시간으로 1분봉 데이터 120개를 무작위 종목(또는 지정 종목)에 대해 가져온 후,
    현재 DB(minute_ohlcv)에 적재된 데이터와 가격, 거래량 등이 100% 일치하는지 정합성을 검증합니다.
    """
    from core.database import connect_sqlite
    from tasks.minute_ohlcv_scheduler import fetch_minute_data
    from datetime import datetime

    conn = connect_sqlite()
    try:
        cursor = conn.cursor()
        
        # 1. 종목 지정이 없으면 DB에 있는 종목 중 무작위 1개 추출
        if not ticker:
            cursor.execute("SELECT DISTINCT ticker FROM minute_ohlcv ORDER BY RANDOM() LIMIT 1")
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No tickers found in DB.")
            ticker = row['ticker']

        # 2. KIS API 호출 (가장 최신 시간 기준 120개)
        now = datetime.now()
        target_date = now.strftime("%Y%m%d")
        target_time = now.strftime("%H%M00")
        
        api_df = await fetch_minute_data(ticker, target_date, target_time)
        if api_df.empty:
            raise HTTPException(status_code=400, detail=f"Failed to fetch API data for {ticker}")

        # 3. 데이터 검증 (API 결과 vs DB 결과)
        total_api_candles = len(api_df)
        match_count = 0
        mismatch_count = 0
        missing_in_db_count = 0
        mismatch_details = []

        for _, row in api_df.iterrows():
            date_val = row.get("stck_bsop_date")
            time_val = row.get("stck_cntg_hour")
            api_close = int(row.get("stck_prpr", 0))
            api_volume = int(row.get("cntg_vol", 0))

            # DB 조회
            cursor.execute(
                "SELECT close, volume FROM minute_ohlcv WHERE ticker = ? AND date = ? AND time = ?",
                (ticker, date_val, time_val)
            )
            db_row = cursor.fetchone()

            if not db_row:
                missing_in_db_count += 1
                continue

            db_close = db_row['close']
            db_volume = db_row['volume']

            if api_close == db_close and api_volume == db_volume:
                match_count += 1
            else:
                mismatch_count += 1
                mismatch_details.append({
                    "date": date_val,
                    "time": time_val,
                    "api": {"close": api_close, "volume": api_volume},
                    "db": {"close": db_close, "volume": db_volume}
                })

        return {
            "test_target_ticker": ticker,
            "total_api_candles_fetched": total_api_candles,
            "result_summary": {
                "perfect_match": match_count,
                "data_mismatch": mismatch_count,
                "missing_in_db": missing_in_db_count
            },
            "status": "PASS (100% Match)" if match_count == total_api_candles else "FAIL (Mismatches or Missing Found)",
            "mismatch_details": mismatch_details[:10]  # 최대 10개만 표출
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification Error: {e}")
    finally:
        conn.close()
