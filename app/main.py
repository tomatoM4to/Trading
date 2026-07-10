import logging
from contextlib import asynccontextmanager
from datetime import datetime

from core.database import init_sqlite_connection
from core.kis_fetch import start_q_worker, stop_q_worker
from core.logging import setup_logging
from core.scheduler import SystemScheduler
from fastapi import FastAPI
from routes import admin, market

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")

    from tasks.init_stock_codes import init_stock_codes_db

    # DB 연결성 확인 및 초기화
    try:
        init_sqlite_connection()
        logger.info("Database connection validated")

        # 종목 리스트 초기화 (KOSPI, KOSDAQ 마스터 파일 다운로드 및 DB 저장)
        init_stock_codes_db()
    except Exception as e:
        logger.error(
            "Failed to connect to the database or initialize stock codes: %s", e
        )
        raise e

    system_scheduler = SystemScheduler()
    system_scheduler.start()

    # KIS API Rate Limit 제어 워커 백그라운드 구동
    await start_q_worker()

    yield  # Application runs here

    # Shutdown code
    logger.info("Application shutting down...")
    await stop_q_worker()
    system_scheduler.stop()


app = FastAPI(
    title="Trading Server",
    lifespan=lifespan,
)

app.include_router(market.router)
app.include_router(admin.router)


@app.get("/")
def read_root():
    logger.debug("read_root endpoint called")
    return {"Hello": "World"}


@app.get("/health")
def health_check():
    logger.debug("health_check endpoint called")
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "app": "Trading Server",
    }
