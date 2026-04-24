"""
FastAPI application entry point.
Manages lifecycle (startup/shutdown), middleware, and route registration.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db.database import init_db, close_db
from app.routes.telegram_webhook import router as webhook_router
from app.scheduler.jobs import setup_scheduler, get_scheduler
from app.services.telegram_service import set_webhook, close_client
from app.exceptions.custom_exceptions import ExpenseTrackerError
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # 0. Validate all required environment variables BEFORE anything else
    from app.config import validate_settings_on_startup
    settings = validate_settings_on_startup()

    logger.info(f"Starting AI Expense Tracker ({settings.APP_ENV})")
    logger.info("\n" + settings.log_config_summary())

    # 1. Initialize database (Neon PostgreSQL)
    init_db()
    logger.info("✅ Database initialized (Neon PostgreSQL)")

    # 2. Set Telegram webhook
    if settings.WEBHOOK_BASE_URL:
        try:
            await set_webhook(settings.webhook_url)
            logger.info(f"✅ Webhook set to {settings.webhook_url}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to set webhook (non-fatal): {e}")

    # 3. Start scheduler
    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("✅ Scheduler started")

    logger.info("✅ Application startup complete")

    yield  # App is running

    # --- Shutdown ---
    logger.info("Shutting down...")

    # Stop scheduler
    sched = get_scheduler()
    if sched and sched.running:
        sched.shutdown(wait=False)
        logger.info("Scheduler stopped")

    # Close HTTP client
    await close_client()

    # Close database
    close_db()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


app = FastAPI(
    title="AI Expense Tracker",
    description=(
        "AI-powered expense tracking via Telegram Bot. "
        "Uses Google Gemini for natural language parsing and receipt OCR."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(webhook_router, tags=["Telegram Webhook"])


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------


@app.exception_handler(ExpenseTrackerError)
async def expense_tracker_error_handler(request: Request, exc: ExpenseTrackerError):
    logger.error(f"Application error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": exc.user_message},
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------


@app.get("/", tags=["System"])
async def root():
    """Root endpoint — API info."""
    return {
        "service": "AI Expense Tracker",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
