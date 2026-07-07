from fastapi import APIRouter, HTTPException
from tasks.daily_ohlcv_scheduler import start_scheduler_task, stop_scheduler_task

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
def cancel_daily_ohlcv():
    """
    현재 구동 중인 1일봉 데이터 수집 스케줄러 태스크를 강제로 중지합니다.
    """
    stopped = stop_scheduler_task()
    if stopped:
        return {"message": "Successfully stopped the running scheduler."}
    else:
        return {"message": "No running scheduler found to stop."}

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
