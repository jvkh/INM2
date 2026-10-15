"""FastAPI application entry point."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request

from common.database import Database
from common.logging_setup import configure_file_logging
from common.version import APP_VERSION
from api.auth import auth_middleware_response, validate_auth_config
from api.auth import router as auth_router
from api.actors import router as actors_router
from api.bursts import router as bursts_router
from api.categories import router as categories_router
from api.requests import router as requests_router
from api.request_counts import router as request_counts_router
from api.status import router as status_router
from api.errors import register_error_handlers
from api.hosts import router as hosts_router
from api.params import router as params_router
from api.operations import router as operations_router
from api.notifications import router as notifications_router
from api.metric_trends import router as metric_trends_router
from api.request_paths import router as request_paths_router
from api.logging_view import router as logging_router
from api.statistics import router as statistics_router

configure_file_logging("api")

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Try to open the database without preventing the API from starting."""
    validate_auth_config()
    logger.info("API started; opening database connection")
    app.state.database = None
    try:
        app.state.database = Database()
        logger.info("API database connection ready")
    except Exception:
        logger.exception("Could not open the API database")
    try:
        yield
    finally:
        if app.state.database is not None:
            app.state.database.close()
        logger.info("API stopped")


app = FastAPI(
    title="Internet Noise Monitor API",
    version=APP_VERSION,
    lifespan=lifespan,
)


@app.middleware("http")
async def require_admin_session(request: Request, call_next):
    rejection = auth_middleware_response(request)
    if rejection is not None:
        return rejection
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", "no-store")
    return response


app.include_router(auth_router, prefix="/api/v1")
app.include_router(requests_router, prefix="/api/v1")
app.include_router(actors_router, prefix="/api/v1")
app.include_router(bursts_router, prefix="/api/v1")
app.include_router(categories_router, prefix="/api/v1")
app.include_router(hosts_router, prefix="/api/v1")
app.include_router(params_router, prefix="/api/v1")
app.include_router(operations_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(metric_trends_router, prefix="/api/v1")
app.include_router(request_paths_router, prefix="/api/v1")
app.include_router(statistics_router, prefix="/api/v1")
app.include_router(logging_router, prefix="/api/v1")
app.include_router(status_router, prefix="/api/v1")
app.include_router(request_counts_router, prefix="/api/v1")
register_error_handlers(app)
