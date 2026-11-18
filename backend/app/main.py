"""Rocket Genie HR & Employee Management System - FastAPI application."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core.config import settings
from app.core.dependencies import ApiRuleError
from app.services import file_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
)
logger = logging.getLogger("rocketgenie")

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    file_service.ensure_dirs()
    logger.info("%s starting (env=%s)", settings.APP_NAME, settings.APP_ENV)
    logger.info("Upload directory: %s", settings.upload_path)
    autogen_task = None
    if settings.SALARY_AUTOGEN_ENABLED:
        import asyncio
        from app.services import salary_autogen_service
        autogen_task = asyncio.create_task(
            salary_autogen_service.scheduler_loop(settings.SALARY_AUTOGEN_INTERVAL_MINUTES)
        )
        logger.info("Monthly salary auto-generation: every %s min", settings.SALARY_AUTOGEN_INTERVAL_MINUTES)
    yield
    if autogen_task is not None:
        autogen_task.cancel()
    logger.info("%s shutting down", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "HR & Employee Management System for Rocket Genie. "
        "Python + FastAPI + PostgreSQL backend serving an HTML/CSS/vanilla-JS frontend."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Turn Pydantic's nested errors into one readable sentence for the UI.

    Pydantic's raw error dicts carry the offending input and a ctx object, which
    may hold values stdlib json can't encode (Decimal, exceptions). Only the
    location and message are passed through, as plain strings.
    """
    raw = exc.errors()
    first = raw[0] if raw else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
    message = str(first.get("msg", "Invalid input.")).replace("Value error, ", "")
    safe_errors = [
        {
            "field": ".".join(str(p) for p in error.get("loc", [])[1:]),
            "message": str(error.get("msg", "")),
        }
        for error in raw[:6]
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": f"{field}: {message}", "errors": safe_errors},
    )


@app.exception_handler(ApiRuleError)
async def rule_error_handler(request: Request, exc: ApiRuleError):
    from fastapi.encoders import jsonable_encoder
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder({"detail": exc.detail, "code": exc.code, "context": exc.context}),
    )


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}


app.include_router(api_router, prefix=settings.API_PREFIX)

# Serving the frontend from the API origin keeps everything on one port in
# development. A separate static host (nginx, Live Server) works just as well:
# set FRONTEND_BASE_URL and CORS_ORIGINS accordingly.
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/app/login.html")
