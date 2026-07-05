import logging
from contextlib import asynccontextmanager
from datetime import datetime

from core.logging import setup_logging
from fastapi import FastAPI
from tasks.auth_scheduler import AuthScheduler

setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    auth_scheduler = AuthScheduler()
    auth_scheduler.start()

    yield  # Application runs here

    # Shutdown code
    logger.info("Application shutting down...")
    auth_scheduler.stop()


app = FastAPI(
    title="Trading Server",
    lifespan=lifespan,
)


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