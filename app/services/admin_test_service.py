import os
from pathlib import Path

from core.database import connect_sqlite, init_sqlite_connection, test_db_var
from fastapi import HTTPException
from services.admin_daily_service import verify_daily_integrity_service
from services.admin_minute_service import verify_minute_integrity_service
from tasks.daily_ohlcv_scheduler import run_daily_ohlcv_scheduler
from tasks.minute_ohlcv_scheduler import (
    run_minute_backfill_task,
)


async def test_daily_scheduler_integration_service():
    # 1. 원본 DB에서 무작위 3종목 추출
    conn_real = connect_sqlite()  # test_db_var is None => trading.db
    try:
        cursor_real = conn_real.cursor()
        cursor_real.execute("SELECT * FROM stock_codes ORDER BY RANDOM() LIMIT 3")
        target_stocks = [dict(row) for row in cursor_real.fetchall()]
        if not target_stocks:
            raise HTTPException(status_code=404, detail="No stocks found in real DB")
    finally:
        conn_real.close()

    # 2. ContextVar 설정하여 이후 모든 DB 연결이 test_trading.db를 바라보게 함
    test_db_path = str(Path(__file__).resolve().parents[2] / "data" / "test_trading.db")

    # 테스트 전 기존 test_trading.db 삭제하여 깨끗한 환경 유지
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    token = test_db_var.set(test_db_path)
    try:
        # 스키마 초기화 (test_db_var 컨텍스트 내이므로 test_trading.db에 생성됨)
        init_sqlite_connection()

        # 3. 추출한 3개 종목을 test_trading.db의 stock_codes에 이식
        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            cursor_test.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_codes (
                    ticker TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    is_halted INTEGER DEFAULT 0
                )
                """
            )
            for s in target_stocks:
                cursor_test.execute(
                    "INSERT INTO stock_codes (ticker, name, market) VALUES (?, ?, ?)",
                    (s["ticker"], s["name"], s["market"]),
                )
            conn_test.commit()
        finally:
            conn_test.close()

        results = {"target_stocks": [s["ticker"] for s in target_stocks]}

        # 4. [검증 1] 콜드스타트
        await run_daily_ohlcv_scheduler(market="KOSPI")
        await run_daily_ohlcv_scheduler(market="KOSDAQ")

        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            cursor_test.execute(
                "SELECT ticker, COUNT(*) FROM daily_ohlcv GROUP BY ticker"
            )
            results["step1_cold_start_counts"] = dict(cursor_test.fetchall())
        finally:
            conn_test.close()

        # 5. [검증 2] 최근 30영업일 치 고의 삭제(슬라이싱) 후 복구 검증
        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            for ticker in results["target_stocks"]:
                cursor_test.execute(
                    """
                    DELETE FROM daily_ohlcv
                    WHERE ticker = ? AND date IN (
                        SELECT date FROM daily_ohlcv WHERE ticker = ? ORDER BY date DESC LIMIT 30
                    )
                    """,
                    (ticker, ticker),
                )
            conn_test.commit()

            cursor_test.execute(
                "SELECT ticker, COUNT(*) FROM daily_ohlcv GROUP BY ticker"
            )
            results["step2_deleted_counts"] = dict(cursor_test.fetchall())
        finally:
            conn_test.close()

        # 스케줄러 재구동하여 빈 공간(Gap) 복구
        await run_daily_ohlcv_scheduler(market="KOSPI")
        await run_daily_ohlcv_scheduler(market="KOSDAQ")

        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            cursor_test.execute(
                "SELECT ticker, COUNT(*) FROM daily_ohlcv GROUP BY ticker"
            )
            results["step2_recovered_counts"] = dict(cursor_test.fetchall())
        finally:
            conn_test.close()

        # 6. [검증 3] API 데이터와 1:1 무결성 비교
        kospi_count = sum(1 for s in target_stocks if s["market"] == "KOSPI")
        kosdaq_count = sum(1 for s in target_stocks if s["market"] == "KOSDAQ")

        verify_results = {}
        if kospi_count > 0:
            verify_results["KOSPI"] = await verify_daily_integrity_service(
                sample_size=kospi_count, market="KOSPI"
            )
        if kosdaq_count > 0:
            verify_results["KOSDAQ"] = await verify_daily_integrity_service(
                sample_size=kosdaq_count, market="KOSDAQ"
            )

        results["step3_integrity_verification"] = verify_results

        return results

    finally:
        # 컨텍스트 복원 (다른 API 호출에 영향을 주지 않음)
        test_db_var.reset(token)


async def test_minute_scheduler_integration_service():
    # 1. 원본 DB에서 무작위 3종목 추출
    conn_real = connect_sqlite()
    try:
        cursor_real = conn_real.cursor()
        cursor_real.execute("SELECT * FROM stock_codes ORDER BY RANDOM() LIMIT 3")
        target_stocks = [dict(row) for row in cursor_real.fetchall()]
        if not target_stocks:
            raise HTTPException(status_code=404, detail="No stocks found in real DB")
    finally:
        conn_real.close()

    test_db_path = str(Path(__file__).resolve().parents[2] / "data" / "test_trading.db")

    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    token = test_db_var.set(test_db_path)
    try:
        init_sqlite_connection()

        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            cursor_test.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_codes (
                    ticker TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    is_halted INTEGER DEFAULT 0
                )
                """
            )
            for s in target_stocks:
                cursor_test.execute(
                    "INSERT INTO stock_codes (ticker, name, market) VALUES (?, ?, ?)",
                    (s["ticker"], s["name"], s["market"]),
                )
            conn_test.commit()
        finally:
            conn_test.close()

        results = {"target_stocks": [s["ticker"] for s in target_stocks]}

        # 4. [검증 1] 콜드스타트 백필 실행
        await run_minute_backfill_task(markets=["KOSPI", "KOSDAQ"], limit_days=3)

        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            cursor_test.execute(
                "SELECT ticker, COUNT(*) FROM minute_ohlcv GROUP BY ticker"
            )
            results["step1_cold_start_counts"] = dict(cursor_test.fetchall())
        finally:
            conn_test.close()

        # 5. [검증 2] 최근 30개 분봉 고의 삭제 후 복구 검증
        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            for ticker in results["target_stocks"]:
                cursor_test.execute(
                    """
                    DELETE FROM minute_ohlcv
                    WHERE ticker = ? AND (date || time) IN (
                        SELECT date || time FROM minute_ohlcv WHERE ticker = ? ORDER BY date DESC, time DESC LIMIT 30
                    )
                    """,
                    (ticker, ticker),
                )
            conn_test.commit()

            cursor_test.execute(
                "SELECT ticker, COUNT(*) FROM minute_ohlcv GROUP BY ticker"
            )
            results["step2_deleted_counts"] = dict(cursor_test.fetchall())
        finally:
            conn_test.close()

        # 갭필 복구
        await run_minute_backfill_task(markets=["KOSPI", "KOSDAQ"], limit_days=3)

        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            cursor_test.execute(
                "SELECT ticker, COUNT(*) FROM minute_ohlcv GROUP BY ticker"
            )
            results["step2_recovered_counts"] = dict(cursor_test.fetchall())
        finally:
            conn_test.close()

        # 6. [검증 3] API 데이터와 1:1 무결성 비교
        kospi_count = sum(1 for s in target_stocks if s["market"] == "KOSPI")
        kosdaq_count = sum(1 for s in target_stocks if s["market"] == "KOSDAQ")

        verify_results = {}
        if kospi_count > 0:
            verify_results["KOSPI"] = await verify_minute_integrity_service(
                sample_size=kospi_count, market="KOSPI"
            )
        if kosdaq_count > 0:
            verify_results["KOSDAQ"] = await verify_minute_integrity_service(
                sample_size=kosdaq_count, market="KOSDAQ"
            )

        results["step3_integrity_verification"] = verify_results

        return results

    finally:
        test_db_var.reset(token)
