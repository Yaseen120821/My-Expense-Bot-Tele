"""
Pytest configuration and shared fixtures.
Uses SQLite in-memory for unit tests (via aiosqlite).
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# --- Set test environment BEFORE importing app modules ---
os.environ["TELEGRAM_BOT_TOKEN"] = "test_token_123"
os.environ["GEMINI_API_KEY"] = "test_gemini_key_123"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["APP_ENV"] = "test"
os.environ["WEBHOOK_BASE_URL"] = "https://test.example.com"
os.environ["RESEND_API_KEY"] = ""
os.environ["EMAIL_FROM"] = ""
os.environ["LOG_LEVEL"] = "WARNING"

from app.db.database import Base
from app.models.user import User
from app.models.expense import Expense, ExpenseSource, PendingConfirmation


# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create a fresh in-memory SQLite engine per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db(db_engine):
    """Provide an async session for each test."""
    factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Factory fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        id=uuid.uuid4(),
        telegram_id=123456789,
        first_name="TestUser",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def test_user_with_expenses(db: AsyncSession, test_user: User) -> User:
    """Create a test user with sample expenses."""
    now = datetime.now(timezone.utc)
    expenses = [
        Expense(
            user_id=test_user.id,
            amount=200.0,
            category="Food",
            description="lunch",
            date=now,
            source=ExpenseSource.TEXT,
        ),
        Expense(
            user_id=test_user.id,
            amount=150.0,
            category="Transport",
            description="uber",
            date=now,
            source=ExpenseSource.TEXT,
        ),
        Expense(
            user_id=test_user.id,
            amount=50.0,
            category="Coffee",
            description="starbucks",
            date=now,
            source=ExpenseSource.TEXT,
        ),
        Expense(
            user_id=test_user.id,
            amount=500.0,
            category="Food",
            description="dinner",
            date=now - timedelta(days=1),
            source=ExpenseSource.TEXT,
        ),
        Expense(
            user_id=test_user.id,
            amount=100.0,
            category="Transport",
            description="metro",
            date=now - timedelta(days=2),
            source=ExpenseSource.TEXT,
        ),
    ]
    for e in expenses:
        db.add(e)
    await db.flush()
    return test_user


# ---------------------------------------------------------------------------
# Mock fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_gemini_expense_response():
    """Mock Gemini response for expense parsing."""
    return [
        {
            "amount": 200.0,
            "category": "Food",
            "description": "lunch at restaurant",
            "date": "2026-04-25",
        }
    ]


@pytest.fixture
def mock_gemini_multi_expense_response():
    """Mock Gemini response for multiple expenses."""
    return [
        {"amount": 50.0, "category": "Coffee", "description": "coffee", "date": "2026-04-25"},
        {"amount": 150.0, "category": "Transport", "description": "uber", "date": "2026-04-25"},
    ]


@pytest.fixture
def mock_gemini_receipt_response():
    """Mock Gemini Vision response for receipt parsing."""
    return {
        "amount": 540.0,
        "items": ["Chicken Biryani", "Naan", "Cold Drink"],
        "category": "Food",
        "confidence": 0.92,
    }


@pytest.fixture
def mock_telegram_text_update():
    """Mock Telegram text message update."""
    return {
        "update_id": 100001,
        "message": {
            "message_id": 1,
            "from": {"id": 123456789, "first_name": "Test", "is_bot": False},
            "chat": {"id": 123456789, "type": "private"},
            "date": 1714000000,
            "text": "spent 200 on lunch",
        },
    }


@pytest.fixture
def mock_telegram_command_update():
    """Mock Telegram command update."""
    return {
        "update_id": 100002,
        "message": {
            "message_id": 2,
            "from": {"id": 123456789, "first_name": "Test", "is_bot": False},
            "chat": {"id": 123456789, "type": "private"},
            "date": 1714000000,
            "text": "/today",
        },
    }


@pytest.fixture
def mock_telegram_photo_update():
    """Mock Telegram photo message update."""
    return {
        "update_id": 100003,
        "message": {
            "message_id": 3,
            "from": {"id": 123456789, "first_name": "Test", "is_bot": False},
            "chat": {"id": 123456789, "type": "private"},
            "date": 1714000000,
            "photo": [
                {"file_id": "small_id", "width": 90, "height": 90, "file_size": 1000},
                {"file_id": "medium_id", "width": 320, "height": 320, "file_size": 5000},
                {"file_id": "large_id", "width": 800, "height": 800, "file_size": 20000},
            ],
        },
    }


@pytest.fixture
def sample_receipt_image():
    """Create a minimal valid PNG for testing."""
    from PIL import Image
    import io

    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# pytest markers
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-integration"):
        skip_integration = pytest.mark.skip(reason="Need --run-integration to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)
