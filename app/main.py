from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import auth, budgets, categories, health, reports, transactions, users
from app.config import get_settings
from app.core.errors import ErrorResponse, register_error_handlers
from app.db.init_db import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="REST API for tracking personal income, expenses, budgets and spending reports.",
        debug=settings.debug,
        lifespan=lifespan,
        responses={
            401: {"model": ErrorResponse, "description": "Missing or invalid token"},
            422: {"model": ErrorResponse, "description": "Validation error"},
        },
    )
    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(categories.router, prefix="/api/v1")
    app.include_router(transactions.router, prefix="/api/v1")
    app.include_router(budgets.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"message": f"Welcome to {settings.app_name}", "docs": "/docs"}

    return app


app = create_app()
