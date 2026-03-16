from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.storage import ensure_dirs
from app.api.routers import health, loading


def create_app() -> FastAPI:
    ensure_dirs()
    app = FastAPI(title="RAG Document System", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(loading.router, prefix="/api/load", tags=["load"])
    return app


app = create_app()

