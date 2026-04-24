"""
Expense CRUD operations and business logic.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, func, delete, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense, ExpenseSource, PendingConfirmation
from app.models.user import User
from app.exceptions.custom_exceptions import DatabaseError
from app.utils.logger import get_logger
from app.utils.helpers import get_user_timezone, now_local, parse_date_string

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


async def get_or_create_user(
    db: AsyncSession, telegram_id: int, first_name: str | None = None
) -> User:
    """Find existing user by telegram_id or create a new one."""
    try:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                telegram_id=telegram_id,
                first_name=first_name,
            )
            db.add(user)
            await db.flush()
            logger.info(f"Created new user: telegram_id={telegram_id}")
        else:
            # Update first_name if provided
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                await db.flush()

        return user

    except Exception as e:
        logger.error(f"Error in get_or_create_user: {e}")
        raise DatabaseError(f"User lookup/creation failed: {e}")


async def get_all_users(db: AsyncSession) -> list[User]:
    """Return all registered users (for scheduled reports)."""
    stmt = select(User)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Expense CRUD
# ---------------------------------------------------------------------------


async def add_expense(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: float,
    category: str,
    date: datetime | str | None = None,
    description: str | None = None,
    source: ExpenseSource = ExpenseSource.TEXT,
) -> Expense:
    """Insert a new expense record."""
    try:
        # Resolve date
        if date is None:
            expense_date = now_local()
        elif isinstance(date, str):
            expense_date = parse_date_string(date)
        else:
            expense_date = date

        expense = Expense(
            user_id=user_id,
            amount=round(amount, 2),
            category=category,
            description=description,
            date=expense_date,
            source=source,
        )
        db.add(expense)
        await db.flush()

        logger.info(
            f"Added expense: ₹{amount} ({category}) for user {user_id}"
        )
        return expense

    except Exception as e:
        logger.error(f"Error adding expense: {e}")
        raise DatabaseError(f"Failed to add expense: {e}")


async def get_expenses(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    category: str | None = None,
) -> list[Expense]:
    """Retrieve expenses with optional date range and category filter."""
    try:
        conditions = [Expense.user_id == user_id]

        if start_date:
            conditions.append(Expense.date >= start_date)
        if end_date:
            conditions.append(Expense.date <= end_date)
        if category:
            conditions.append(func.lower(Expense.category) == category.lower())

        stmt = (
            select(Expense)
            .where(and_(*conditions))
            .order_by(Expense.date.desc(), Expense.created_at.desc())
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    except Exception as e:
        logger.error(f"Error fetching expenses: {e}")
        raise DatabaseError(f"Failed to fetch expenses: {e}")


async def get_expenses_by_category(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, float]:
    """Aggregate expenses by category for a date range."""
    try:
        stmt = (
            select(Expense.category, func.sum(Expense.amount))
            .where(
                and_(
                    Expense.user_id == user_id,
                    Expense.date >= start_date,
                    Expense.date <= end_date,
                )
            )
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
        )

        result = await db.execute(stmt)
        rows = result.all()
        return {row[0]: float(row[1]) for row in rows}

    except Exception as e:
        logger.error(f"Error fetching category totals: {e}")
        raise DatabaseError(f"Failed to fetch category totals: {e}")


async def get_daily_totals(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, float]:
    """Get total spending per day over a date range."""
    try:
        stmt = (
            select(
                func.date(Expense.date).label("day"),
                func.sum(Expense.amount).label("total"),
            )
            .where(
                and_(
                    Expense.user_id == user_id,
                    Expense.date >= start_date,
                    Expense.date <= end_date,
                )
            )
            .group_by(func.date(Expense.date))
            .order_by(func.date(Expense.date))
        )

        result = await db.execute(stmt)
        rows = result.all()
        return {str(row[0]): float(row[1]) for row in rows}

    except Exception as e:
        logger.error(f"Error fetching daily totals: {e}")
        raise DatabaseError(f"Failed to fetch daily totals: {e}")


async def get_total(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_date: datetime,
    end_date: datetime,
) -> float:
    """Get total spending for a date range."""
    try:
        stmt = (
            select(func.sum(Expense.amount))
            .where(
                and_(
                    Expense.user_id == user_id,
                    Expense.date >= start_date,
                    Expense.date <= end_date,
                )
            )
        )
        result = await db.execute(stmt)
        total = result.scalar_one_or_none()
        return float(total) if total else 0.0

    except Exception as e:
        logger.error(f"Error fetching total: {e}")
        raise DatabaseError(f"Failed to fetch total: {e}")


async def delete_last_expense(
    db: AsyncSession, user_id: uuid.UUID
) -> Expense | None:
    """Delete the most recently created expense for a user. Returns the deleted expense."""
    try:
        stmt = (
            select(Expense)
            .where(Expense.user_id == user_id)
            .order_by(Expense.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        expense = result.scalar_one_or_none()

        if expense:
            await db.delete(expense)
            await db.flush()
            logger.info(f"Deleted last expense for user {user_id}: {expense}")

        return expense

    except Exception as e:
        logger.error(f"Error deleting expense: {e}")
        raise DatabaseError(f"Failed to delete expense: {e}")


async def get_expense_count(
    db: AsyncSession, user_id: uuid.UUID
) -> int:
    """Get total number of expenses for a user."""
    stmt = select(func.count()).select_from(Expense).where(Expense.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Pending Confirmation (receipt flow)
# ---------------------------------------------------------------------------


async def store_pending_confirmation(
    db: AsyncSession,
    user_id: uuid.UUID,
    chat_id: int,
    data: dict,
) -> PendingConfirmation:
    """Store parsed receipt data pending user confirmation."""
    try:
        # Remove any existing pending confirmation for this user
        await clear_pending_confirmation(db, user_id)

        pending = PendingConfirmation(
            user_id=user_id,
            telegram_chat_id=chat_id,
            data=data,
        )
        db.add(pending)
        await db.flush()

        logger.info(f"Stored pending confirmation for user {user_id}")
        return pending

    except Exception as e:
        logger.error(f"Error storing pending confirmation: {e}")
        raise DatabaseError(f"Failed to store pending confirmation: {e}")


async def get_pending_confirmation(
    db: AsyncSession, user_id: uuid.UUID
) -> PendingConfirmation | None:
    """Retrieve pending confirmation for a user."""
    stmt = (
        select(PendingConfirmation)
        .where(PendingConfirmation.user_id == user_id)
        .order_by(PendingConfirmation.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def clear_pending_confirmation(
    db: AsyncSession, user_id: uuid.UUID
) -> None:
    """Remove all pending confirmations for a user."""
    stmt = delete(PendingConfirmation).where(
        PendingConfirmation.user_id == user_id
    )
    await db.execute(stmt)
    await db.flush()


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------


async def detect_anomalies(
    db: AsyncSession,
    user_id: uuid.UUID,
    new_amount: float,
) -> str | None:
    """
    Flag if a new expense is >2 standard deviations from the user's daily average.
    Returns a warning message or None.
    """
    try:
        # Get average and stddev of daily totals for last 30 days
        tz = get_user_timezone()
        end = now_local()
        start = end - timedelta(days=30)

        stmt = (
            select(
                func.avg(Expense.amount).label("avg"),
                func.stddev(Expense.amount).label("stddev"),
            )
            .where(
                and_(
                    Expense.user_id == user_id,
                    Expense.date >= start,
                    Expense.date <= end,
                )
            )
        )
        result = await db.execute(stmt)
        row = result.one_or_none()

        if row and row.avg and row.stddev:
            avg = float(row.avg)
            stddev = float(row.stddev)
            if stddev > 0 and new_amount > avg + 2 * stddev:
                return (
                    f"⚠️ This expense (₹{new_amount:,.2f}) is unusually high "
                    f"compared to your average (₹{avg:,.2f})."
                )

        return None

    except Exception:
        # Non-critical — don't break the flow
        return None
