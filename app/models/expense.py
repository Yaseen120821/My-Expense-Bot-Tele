"""
Expense and PendingConfirmation models.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class ExpenseSource(str, enum.Enum):
    """How the expense was recorded."""
    TEXT = "text"
    IMAGE = "image"


class Expense(Base):
    """A single expense record."""

    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    category: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source: Mapped[ExpenseSource] = mapped_column(
        Enum(ExpenseSource, name="expense_source"),
        nullable=False,
        default=ExpenseSource.TEXT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="expenses")

    # Composite index for report queries
    __table_args__ = (
        Index("ix_expenses_user_date", "user_id", "date"),
    )

    def __repr__(self) -> str:
        return f"<Expense ₹{self.amount} ({self.category}) on {self.date}>"


class PendingConfirmation(Base):
    """
    Temporary storage for receipt data awaiting user confirmation.
    Entries expire and are cleaned up periodically.
    """

    __tablename__ = "pending_confirmations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    telegram_chat_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )
    data: Mapped[dict] = mapped_column(
        JSON, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="pending_confirmations")

    def __repr__(self) -> str:
        return f"<PendingConfirmation user_id={self.user_id}>"
