import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from core.database import init_sqlite_connection
from core.kis_fetch import start_q_worker, stop_q_worker
from core.logging import setup_logging
from core.scheduler import SystemScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import admin, market, screener

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os

    from core.bootstrap import run_bootstrap_pipeline
    from dotenv import load_dotenv

    # python-dotenv 문서에 따라 .env 파일 로드 (Source: https://github.com/theskumar/python-dotenv)
    load_dotenv()

    logger.info("Application starting up...")

    # DB 연결성 확인 및 초기화
    try:
        init_sqlite_connection()
        logger.info("Database connection validated")
    except Exception as e:
        logger.error("Failed to connect to the database: %s", e)
        raise e

    # KIS API Rate Limit 제어 워커 백그라운드 구동 (모든 통신에 필수)
    await start_q_worker()

    is_debug = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    is_sched = os.getenv("SCHED", "False").lower() in ("true", "1", "t")

    from core.kis_auth import auth

    # 1. KIS API Auth 토큰 초기화
    if is_debug:
        logger.info("DEBUG mode is ON: Reusing cached auth token (force=False)")
        await asyncio.to_thread(auth, force=False)
    else:
        logger.info("DEBUG mode is OFF: Forcing new auth token issuance (force=True)")
        await asyncio.to_thread(auth, force=True)

    system_scheduler = None

    # 2. 백그라운드 스케줄러 & 부트스트랩 제어
    if is_sched:
        logger.sched(
            "SCHED mode is ON: Starting system scheduler and bootstrap pipeline..."
        )
        system_scheduler = SystemScheduler()
        system_scheduler.start()

        # 부트스트랩 파이프라인 백그라운드 구동 (FastAPI 블로킹 방지)
        asyncio.create_task(run_bootstrap_pipeline())
    else:
        logger.sched(
            "SCHED mode is OFF: Skipping background scheduler and bootstrap tasks."
        )

    yield  # Application runs here

    # Shutdown code
    logger.info("Application shutting down...")
    await stop_q_worker()
    if system_scheduler:
        system_scheduler.stop()


app = FastAPI(
    title="Trading Server",
    lifespan=lifespan,
)

# FastAPI CORS configuration
# Source: https://fastapi.tiangolo.com/tutorial/cors/
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://trading-one-kappa.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router)
app.include_router(admin.router)
app.include_router(screener.router)


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
