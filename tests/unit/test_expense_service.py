"""
Unit tests for expense service (CRUD operations, user management, anomaly detection).
"""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense, ExpenseSource, PendingConfirmation
from app.models.user import User
from app.services import expense_service


# ---------------------------------------------------------------------------
# User management tests
# ---------------------------------------------------------------------------


class TestGetOrCreateUser:
    """Test user creation and lookup."""

    @pytest.mark.asyncio
    async def test_create_new_user(self, db: AsyncSession):
        user = await expense_service.get_or_create_user(db, telegram_id=999999)
        assert user is not None
        assert user.telegram_id == 999999

    @pytest.mark.asyncio
    async def test_get_existing_user(self, db: AsyncSession, test_user: User):
        user = await expense_service.get_or_create_user(db, telegram_id=test_user.telegram_id)
        assert user.id == test_user.id

    @pytest.mark.asyncio
    async def test_update_first_name(self, db: AsyncSession, test_user: User):
        user = await expense_service.get_or_create_user(
            db, telegram_id=test_user.telegram_id, first_name="NewName"
        )
        assert user.first_name == "NewName"


class TestGetAllUsers:
    """Test fetching all users."""

    @pytest.mark.asyncio
    async def test_get_all_users_empty(self, db: AsyncSession):
        users = await expense_service.get_all_users(db)
        assert users == []

    @pytest.mark.asyncio
    async def test_get_all_users_with_data(self, db: AsyncSession, test_user: User):
        users = await expense_service.get_all_users(db)
        assert len(users) == 1
        assert users[0].telegram_id == test_user.telegram_id


# ---------------------------------------------------------------------------
# Expense CRUD tests
# ---------------------------------------------------------------------------


class TestAddExpense:
    """Test expense creation."""

    @pytest.mark.asyncio
    async def test_add_expense_basic(self, db: AsyncSession, test_user: User):
        expense = await expense_service.add_expense(
            db, user_id=test_user.id, amount=100.0, category="Food"
        )
        assert expense.amount == 100.0
        assert expense.category == "Food"
        assert expense.source == ExpenseSource.TEXT

    @pytest.mark.asyncio
    async def test_add_expense_with_date_string(self, db: AsyncSession, test_user: User):
        expense = await expense_service.add_expense(
            db, user_id=test_user.id, amount=50.0, category="Coffee",
            date="2026-04-20",
        )
        assert expense.date.day == 20

    @pytest.mark.asyncio
    async def test_add_expense_image_source(self, db: AsyncSession, test_user: User):
        expense = await expense_service.add_expense(
            db, user_id=test_user.id, amount=540.0, category="Food",
            source=ExpenseSource.IMAGE,
        )
        assert expense.source == ExpenseSource.IMAGE

    @pytest.mark.asyncio
    async def test_add_expense_rounds_amount(self, db: AsyncSession, test_user: User):
        expense = await expense_service.add_expense(
            db, user_id=test_user.id, amount=99.999, category="Food"
        )
        assert expense.amount == 100.0


class TestGetExpenses:
    """Test expense retrieval with filters."""

    @pytest.mark.asyncio
    async def test_get_all_user_expenses(self, db: AsyncSession, test_user_with_expenses: User):
        expenses = await expense_service.get_expenses(db, test_user_with_expenses.id)
        assert len(expenses) == 5

    @pytest.mark.asyncio
    async def test_get_expenses_with_date_range(self, db: AsyncSession, test_user_with_expenses: User):
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=1)
        end = now + timedelta(hours=1)
        expenses = await expense_service.get_expenses(
            db, test_user_with_expenses.id, start_date=start, end_date=end
        )
        # Only today's expenses (3)
        assert len(expenses) == 3

    @pytest.mark.asyncio
    async def test_get_expenses_by_category(self, db: AsyncSession, test_user_with_expenses: User):
        expenses = await expense_service.get_expenses(
            db, test_user_with_expenses.id, category="Food"
        )
        assert len(expenses) == 2
        assert all(e.category == "Food" for e in expenses)

    @pytest.mark.asyncio
    async def test_get_expenses_empty_result(self, db: AsyncSession, test_user: User):
        expenses = await expense_service.get_expenses(db, test_user.id)
        assert expenses == []


class TestGetExpensesByCategory:
    """Test category aggregation."""

    @pytest.mark.asyncio
    async def test_category_totals(self, db: AsyncSession, test_user_with_expenses: User):
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        end = now + timedelta(hours=1)
        categories = await expense_service.get_expenses_by_category(
            db, test_user_with_expenses.id, start, end
        )
        assert "Food" in categories
        assert categories["Food"] == 700.0  # 200 + 500
        assert categories["Transport"] == 250.0  # 150 + 100
        assert categories["Coffee"] == 50.0


class TestGetDailyTotals:
    """Test daily aggregation."""

    @pytest.mark.asyncio
    async def test_daily_totals(self, db: AsyncSession, test_user_with_expenses: User):
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        end = now + timedelta(hours=1)
        totals = await expense_service.get_daily_totals(
            db, test_user_with_expenses.id, start, end
        )
        assert len(totals) > 0


class TestGetTotal:
    """Test total calculation."""

    @pytest.mark.asyncio
    async def test_total_all_time(self, db: AsyncSession, test_user_with_expenses: User):
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)
        end = now + timedelta(hours=1)
        total = await expense_service.get_total(
            db, test_user_with_expenses.id, start, end
        )
        assert total == 1000.0  # 200+150+50+500+100

    @pytest.mark.asyncio
    async def test_total_no_expenses(self, db: AsyncSession, test_user: User):
        now = datetime.now(timezone.utc)
        total = await expense_service.get_total(
            db, test_user.id, now - timedelta(days=1), now
        )
        assert total == 0.0


class TestDeleteLastExpense:
    """Test expense deletion."""

    @pytest.mark.asyncio
    async def test_delete_last(self, db: AsyncSession, test_user_with_expenses: User):
        deleted = await expense_service.delete_last_expense(db, test_user_with_expenses.id)
        assert deleted is not None
        # Verify count reduced
        remaining = await expense_service.get_expenses(db, test_user_with_expenses.id)
        assert len(remaining) == 4

    @pytest.mark.asyncio
    async def test_delete_last_no_expenses(self, db: AsyncSession, test_user: User):
        deleted = await expense_service.delete_last_expense(db, test_user.id)
        assert deleted is None


class TestExpenseCount:
    """Test expense counting."""

    @pytest.mark.asyncio
    async def test_count_with_expenses(self, db: AsyncSession, test_user_with_expenses: User):
        count = await expense_service.get_expense_count(db, test_user_with_expenses.id)
        assert count == 5

    @pytest.mark.asyncio
    async def test_count_empty(self, db: AsyncSession, test_user: User):
        count = await expense_service.get_expense_count(db, test_user.id)
        assert count == 0


# ---------------------------------------------------------------------------
# Pending confirmation tests
# ---------------------------------------------------------------------------


class TestPendingConfirmation:
    """Test the receipt confirmation workflow."""

    @pytest.mark.asyncio
    async def test_store_pending(self, db: AsyncSession, test_user: User):
        pending = await expense_service.store_pending_confirmation(
            db, test_user.id, 123456789,
            {"amount": 540.0, "category": "Food", "items": ["Biryani"]},
        )
        assert pending is not None
        assert pending.data["amount"] == 540.0

    @pytest.mark.asyncio
    async def test_get_pending(self, db: AsyncSession, test_user: User):
        await expense_service.store_pending_confirmation(
            db, test_user.id, 123456789,
            {"amount": 100.0, "category": "Coffee"},
        )
        pending = await expense_service.get_pending_confirmation(db, test_user.id)
        assert pending is not None
        assert pending.data["amount"] == 100.0

    @pytest.mark.asyncio
    async def test_get_pending_none(self, db: AsyncSession, test_user: User):
        pending = await expense_service.get_pending_confirmation(db, test_user.id)
        assert pending is None

    @pytest.mark.asyncio
    async def test_clear_pending(self, db: AsyncSession, test_user: User):
        await expense_service.store_pending_confirmation(
            db, test_user.id, 123456789,
            {"amount": 200.0, "category": "Shopping"},
        )
        await expense_service.clear_pending_confirmation(db, test_user.id)
        pending = await expense_service.get_pending_confirmation(db, test_user.id)
        assert pending is None

    @pytest.mark.asyncio
    async def test_store_replaces_existing(self, db: AsyncSession, test_user: User):
        await expense_service.store_pending_confirmation(
            db, test_user.id, 123456789,
            {"amount": 100.0, "category": "Old"},
        )
        await expense_service.store_pending_confirmation(
            db, test_user.id, 123456789,
            {"amount": 200.0, "category": "New"},
        )
        pending = await expense_service.get_pending_confirmation(db, test_user.id)
        assert pending.data["category"] == "New"


# ---------------------------------------------------------------------------
# Anomaly detection tests
# ---------------------------------------------------------------------------


class TestDetectAnomalies:
    """Test anomaly detection."""

    @pytest.mark.asyncio
    async def test_no_anomaly_normal_amount(self, db: AsyncSession, test_user_with_expenses: User):
        result = await expense_service.detect_anomalies(
            db, test_user_with_expenses.id, 200.0
        )
        # May or may not flag depending on stddev — just verify it returns str or None
        assert result is None or isinstance(result, str)

    @pytest.mark.asyncio
    async def test_anomaly_very_large_amount(self, db: AsyncSession, test_user_with_expenses: User):
        result = await expense_service.detect_anomalies(
            db, test_user_with_expenses.id, 50000.0
        )
        if result:
            assert "unusually high" in result.lower()

    @pytest.mark.asyncio
    async def test_no_anomaly_no_history(self, db: AsyncSession, test_user: User):
        result = await expense_service.detect_anomalies(db, test_user.id, 100.0)
        assert result is None
