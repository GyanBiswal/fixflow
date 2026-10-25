"""FixFlow API entry point."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine
from app.routes import complaints, technicians, workflow

logger = logging.getLogger("fixflow")

app = FastAPI(
    title="FixFlow API",
    version="0.2.0",
    description="AI-powered maintenance coordination agent (backend).",
)

app.include_router(complaints.router)
app.include_router(technicians.router)
app.include_router(workflow.router)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    """Any unexpected database problem returns a safe, generic message."""
    logger.error("Database error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database error. Please try again later."},
    )


@app.get("/health", tags=["Health"])
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "error", "database": "down"})
    return {"status": "ok", "database": "up"}
