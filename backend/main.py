from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import ai, health, loading
from app.services.loading_service import load_document


def create_app() -> FastAPI:
    app = FastAPI(title="RAG Document System", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
    app.include_router(loading.router, prefix="/api/load", tags=["load"])

    @app.post("/load", tags=["load"])
    async def load(
        file: UploadFile = File(...),
        loading_method: str = Form("auto"),
        strategy: str | None = Form(None),
        chunking_strategy: str | None = Form(None),
        chunking_options: str | None = Form(None),
    ) -> dict:
        """
        Upload a document, parse/chunk it, and persist processed JSON.
        """
        try:
            return await load_document(
                file,
                loading_method=loading_method,
                strategy=strategy,
                chunking_strategy=chunking_strategy,
                chunking_options=chunking_options,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


app = create_app()

__all__ = ["app", "create_app"]
