"""
Unit tests for query service (natural language query → DB query → formatted response).
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import query_service
from app.exceptions.custom_exceptions import QueryError


class TestHandleQuery:
    """Test the overall query handling pipeline."""

    @pytest.mark.asyncio
    @patch("app.services.query_service.ai_service")
    @patch("app.services.query_service.expense_service")
    async def test_category_query(self, mock_es, mock_ai, db: AsyncSession, test_user: User):
        mock_ai.interpret_query = AsyncMock(return_value={
            "type": "category_date",
            "start_date": None,
            "end_date": None,
            "category": "Food",
            "period": "week",
        })

        # Mock expense objects
        from unittest.mock import MagicMock
        from datetime import datetime, timezone
        expense_mock = MagicMock()
        expense_mock.amount = 200.0
        expense_mock.category = "Food"
        expense_mock.description = "lunch"
        expense_mock.date = datetime.now(timezone.utc)

        mock_es.get_expenses = AsyncMock(return_value=[expense_mock])

        result = await query_service.handle_query(db, test_user.id, "How much on food this week?")
        assert "Food" in result
        assert "₹" in result

    @pytest.mark.asyncio
    @patch("app.services.query_service.ai_service")
    @patch("app.services.query_service.expense_service")
    async def test_summary_query(self, mock_es, mock_ai, db: AsyncSession, test_user: User):
        mock_ai.interpret_query = AsyncMock(return_value={
            "type": "summary",
            "start_date": None,
            "end_date": None,
            "category": None,
            "period": "month",
        })
        mock_es.get_expenses_by_category = AsyncMock(
            return_value={"Food": 1000.0, "Transport": 500.0}
        )

        result = await query_service.handle_query(db, test_user.id, "Monthly summary")
        assert "Total" in result
        assert "Food" in result

    @pytest.mark.asyncio
    @patch("app.services.query_service.ai_service")
    @patch("app.services.query_service.expense_service")
    async def test_date_range_query(self, mock_es, mock_ai, db: AsyncSession, test_user: User):
        mock_ai.interpret_query = AsyncMock(return_value={
            "type": "date_range",
            "start_date": "2026-04-24",
            "end_date": "2026-04-24",
            "category": None,
            "period": "yesterday",
        })

        from unittest.mock import MagicMock
        from datetime import datetime, timezone
        expense_mock = MagicMock()
        expense_mock.amount = 300.0
        expense_mock.category = "Shopping"
        expense_mock.description = "clothes"
        expense_mock.date = datetime.now(timezone.utc)

        mock_es.get_expenses = AsyncMock(return_value=[expense_mock])

        result = await query_service.handle_query(db, test_user.id, "What did I spend yesterday?")
        assert "₹" in result

    @pytest.mark.asyncio
    @patch("app.services.query_service.ai_service")
    @patch("app.services.query_service.expense_service")
    async def test_empty_result(self, mock_es, mock_ai, db: AsyncSession, test_user: User):
        mock_ai.interpret_query = AsyncMock(return_value={
            "type": "category_filter",
            "start_date": None,
            "end_date": None,
            "category": "Entertainment",
            "period": "week",
        })
        mock_es.get_expenses = AsyncMock(return_value=[])

        result = await query_service.handle_query(db, test_user.id, "Entertainment this week?")
        assert "No" in result

    @pytest.mark.asyncio
    @patch("app.services.query_service.ai_service")
    async def test_query_ai_failure_raises(self, mock_ai, db: AsyncSession, test_user: User):
        mock_ai.interpret_query = AsyncMock(
            side_effect=Exception("AI is down")
        )

        with pytest.raises(QueryError):
            await query_service.handle_query(db, test_user.id, "Some query")
