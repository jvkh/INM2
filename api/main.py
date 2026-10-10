"""FastAPI application entry point."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from common.database import Database
from api.actors import router as actors_router
from api.bursts import router as bursts_router
from api.requests import router as requests_router
from api.status import router as status_router
from api.errors import register_error_handlers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Try to open the database without preventing the API from starting."""
    app.state.database = None
    try:
        app.state.database = Database()
    except Exception:
        logger.exception("Could not open the API database")
    try:
        yield
    finally:
        if app.state.database is not None:
            app.state.database.close()


app = FastAPI(
    title="Internet Noise Monitor API",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(requests_router, prefix="/api/v1")
app.include_router(actors_router, prefix="/api/v1")
app.include_router(bursts_router, prefix="/api/v1")
app.include_router(status_router, prefix="/api/v1")
register_error_handlers(app)
