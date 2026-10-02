import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_documents import router as documents_router
from app.api.routes_evaluation import router as evaluation_router
from app.api.routes_health import router as health_router
from app.api.routes_qa import router as qa_router
from app.core.logging import configure_logging
from app.core.settings import get_settings
from app.documents.service import get_document_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Thread-mode tasks die with the previous API process; fail what they left
    # unfinished so those documents can be removed or re-uploaded. Best effort:
    # an unreachable database must not stop the API from starting, because
    # /ready exists to report exactly that state.
    try:
        get_document_service().recover_interrupted_thread_documents()
    except Exception:
        logger.exception("interrupted_document_recovery_failed")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    app = FastAPI(
        title="IntelliDocs AI",
        description="A production-style portfolio implementation for document intelligence.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(documents_router)
    app.include_router(qa_router)
    app.include_router(evaluation_router)
    return app


app = create_app()
