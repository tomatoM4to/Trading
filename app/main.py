import asyncio
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

    from core.bootstrap import run_bootstrap_pipeline

    # DB 연결성 확인 및 초기화
    try:
        init_sqlite_connection()
        logger.info("Database connection validated")
    except Exception as e:
        logger.error("Failed to connect to the database: %s", e)
        raise e

    system_scheduler = SystemScheduler()
    system_scheduler.start()

    # KIS API Rate Limit 제어 워커 백그라운드 구동
    await start_q_worker()

    # 부트스트랩 파이프라인 백그라운드 구동 (FastAPI 블로킹 방지)
    asyncio.create_task(run_bootstrap_pipeline())

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
