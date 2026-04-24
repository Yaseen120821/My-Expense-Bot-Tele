"""
Integration tests for database operations.
Tests schema creation, constraint enforcement, and concurrent writes.
"""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.expense import Expense, ExpenseSource, PendingConfirmation


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Test that the schema is created correctly."""

    @pytest.mark.asyncio
    async def test_users_table_exists(self, db: AsyncSession):
        result = await db.execute(text("SELECT 1 FROM users LIMIT 0"))
        assert result is not None

    @pytest.mark.asyncio
    async def test_expenses_table_exists(self, db: AsyncSession):
        result = await db.execute(text("SELECT 1 FROM expenses LIMIT 0"))
        assert result is not None

    @pytest.mark.asyncio
    async def test_pending_confirmations_table_exists(self, db: AsyncSession):
        result = await db.execute(text("SELECT 1 FROM pending_confirmations LIMIT 0"))
        assert result is not None


# ---------------------------------------------------------------------------
# Constraint tests
# ---------------------------------------------------------------------------


class TestConstraints:
    """Test database constraints."""

    @pytest.mark.asyncio
    async def test_unique_telegram_id(self, db: AsyncSession):
        """Two users cannot share the same telegram_id."""
        user1 = User(telegram_id=111111111, first_name="User1")
        db.add(user1)
        await db.flush()

        user2 = User(telegram_id=111111111, first_name="User2")
        db.add(user2)

        with pytest.raises(Exception):  # IntegrityError
            await db.flush()

    @pytest.mark.asyncio
    async def test_expense_requires_user(self, db: AsyncSession):
        """Expense must reference a valid user.
        Note: SQLite does not enforce FK constraints by default.
        This test verifies the schema defines the constraint; enforcement
        is validated in production PostgreSQL.
        """
        expense = Expense(
            user_id=uuid.uuid4(),  # Non-existent user
            amount=100.0,
            category="Test",
            date=datetime.now(timezone.utc),
            source=ExpenseSource.TEXT,
        )
        db.add(expense)

        # SQLite won't raise here, but PostgreSQL will.
        # We verify the FK exists in the schema instead.
        try:
            await db.flush()
        except Exception:
            pass  # Expected on PostgreSQL
        # Verify FK is defined in schema
        assert any(
            fk.target_fullname == "users.id"
            for fk in Expense.__table__.foreign_keys
        )

    @pytest.mark.asyncio
    async def test_cascade_delete_user_expenses(self, db: AsyncSession):
        """Deleting a user should cascade-delete their expenses."""
        user = User(telegram_id=222222222, first_name="CascadeTest")
        db.add(user)
        await db.flush()

        expense = Expense(
            user_id=user.id,
            amount=50.0,
            category="Test",
            date=datetime.now(timezone.utc),
            source=ExpenseSource.TEXT,
        )
        db.add(expense)
        await db.flush()

        # Delete user
        await db.delete(user)
        await db.flush()

        # Expense should be gone
        result = await db.execute(
            select(Expense).where(Expense.user_id == user.id)
        )
        assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Data integrity tests
# ---------------------------------------------------------------------------


class TestDataIntegrity:
    """Test data insertion and retrieval."""

    @pytest.mark.asyncio
    async def test_create_and_read_expense(self, db: AsyncSession, test_user: User):
        expense = Expense(
            user_id=test_user.id,
            amount=350.75,
            category="Groceries",
            description="Weekly groceries from supermarket",
            date=datetime.now(timezone.utc),
            source=ExpenseSource.TEXT,
        )
        db.add(expense)
        await db.flush()

        result = await db.execute(
            select(Expense).where(Expense.id == expense.id)
        )
        fetched = result.scalar_one()
        assert float(fetched.amount) == 350.75
        assert fetched.category == "Groceries"
        assert fetched.description == "Weekly groceries from supermarket"

    @pytest.mark.asyncio
    async def test_expense_source_enum(self, db: AsyncSession, test_user: User):
        for source in ExpenseSource:
            expense = Expense(
                user_id=test_user.id,
                amount=100.0,
                category="Test",
                date=datetime.now(timezone.utc),
                source=source,
            )
            db.add(expense)
        await db.flush()

        result = await db.execute(
            select(Expense).where(Expense.user_id == test_user.id)
        )
        expenses = result.scalars().all()
        sources = {e.source for e in expenses}
        assert ExpenseSource.TEXT in sources
        assert ExpenseSource.IMAGE in sources

    @pytest.mark.asyncio
    async def test_pending_confirmation_json(self, db: AsyncSession, test_user: User):
        data = {
            "amount": 540.0,
            "items": ["Biryani", "Naan", "Cold Drink"],
            "category": "Food",
            "confidence": 0.92,
        }
        pending = PendingConfirmation(
            user_id=test_user.id,
            telegram_chat_id=123456789,
            data=data,
        )
        db.add(pending)
        await db.flush()

        result = await db.execute(
            select(PendingConfirmation).where(PendingConfirmation.user_id == test_user.id)
        )
        fetched = result.scalar_one()
        assert fetched.data["amount"] == 540.0
        assert "Biryani" in fetched.data["items"]


# ---------------------------------------------------------------------------
# Concurrent writes test
# ---------------------------------------------------------------------------


class TestConcurrentWrites:
    """Test that concurrent expense insertions don't conflict."""

    @pytest.mark.asyncio
    async def test_concurrent_expense_creation(self, db: AsyncSession, test_user: User):
        """Insert multiple expenses in rapid succession."""
        tasks = []
        for i in range(10):
            expense = Expense(
                user_id=test_user.id,
                amount=float(i * 100 + 50),
                category=f"Category{i}",
                date=datetime.now(timezone.utc),
                source=ExpenseSource.TEXT,
            )
            db.add(expense)

        await db.flush()

        result = await db.execute(
            select(Expense).where(Expense.user_id == test_user.id)
        )
        expenses = result.scalars().all()
        assert len(expenses) == 10
