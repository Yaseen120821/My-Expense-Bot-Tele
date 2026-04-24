"""
Unit tests for report service (daily/weekly/monthly reports, chart generation, comparisons).
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import report_service


# ---------------------------------------------------------------------------
# Daily report tests
# ---------------------------------------------------------------------------


class TestDailyReport:
    """Test daily report generation."""

    @pytest.mark.asyncio
    @patch("app.services.report_service.expense_service")
    async def test_daily_report_with_expenses(self, mock_es, db: AsyncSession, test_user: User):
        mock_es.get_expenses_by_category = AsyncMock(
            return_value={"Food": 500.0, "Transport": 150.0}
        )

        result = await report_service.generate_daily_report(db, test_user.id)
        assert "Today's Summary" in result
        assert "Food" in result
        assert "Transport" in result
        assert "₹" in result

    @pytest.mark.asyncio
    @patch("app.services.report_service.expense_service")
    async def test_daily_report_no_expenses(self, mock_es, db: AsyncSession, test_user: User):
        mock_es.get_expenses_by_category = AsyncMock(return_value={})

        result = await report_service.generate_daily_report(db, test_user.id)
        assert "No expenses" in result


# ---------------------------------------------------------------------------
# Summary text tests
# ---------------------------------------------------------------------------


class TestSummaryText:
    """Test text-based summary generation."""

    @pytest.mark.asyncio
    @patch("app.services.report_service.expense_service")
    async def test_weekly_summary(self, mock_es, db: AsyncSession, test_user: User):
        mock_es.get_expenses_by_category = AsyncMock(
            return_value={"Food": 1200.0, "Coffee": 300.0, "Transport": 800.0}
        )
        mock_es.get_total = AsyncMock(return_value=2000.0)

        result = await report_service.generate_summary_text(db, test_user.id, "week")
        assert "Weekly Summary" in result
        assert "Food" in result
        assert "Total" in result

    @pytest.mark.asyncio
    @patch("app.services.report_service.expense_service")
    async def test_monthly_summary(self, mock_es, db: AsyncSession, test_user: User):
        mock_es.get_expenses_by_category = AsyncMock(
            return_value={"Groceries": 5000.0, "Utilities": 2000.0}
        )
        mock_es.get_total = AsyncMock(return_value=4000.0)

        result = await report_service.generate_summary_text(db, test_user.id, "month")
        assert "Monthly Summary" in result

    @pytest.mark.asyncio
    @patch("app.services.report_service.expense_service")
    async def test_summary_no_expenses(self, mock_es, db: AsyncSession, test_user: User):
        mock_es.get_expenses_by_category = AsyncMock(return_value={})

        result = await report_service.generate_summary_text(db, test_user.id, "week")
        assert "No expenses" in result


# ---------------------------------------------------------------------------
# Chart generation tests
# ---------------------------------------------------------------------------


class TestChartGeneration:
    """Test matplotlib chart generation."""

    def test_create_pie_chart(self):
        data = {"Food": 500.0, "Transport": 200.0, "Coffee": 100.0}
        result = report_service._create_pie_chart(data, "Test Pie")
        assert isinstance(result, bytes)
        assert len(result) > 0
        # Check PNG header
        assert result[:4] == b"\x89PNG"

    def test_create_bar_chart(self):
        data = {
            "2026-04-20": 300.0,
            "2026-04-21": 450.0,
            "2026-04-22": 200.0,
            "2026-04-23": 600.0,
        }
        result = report_service._create_bar_chart(data, "Test Bar")
        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"

    def test_create_pie_chart_single_category(self):
        data = {"Food": 1000.0}
        result = report_service._create_pie_chart(data, "Single")
        assert isinstance(result, bytes)

    def test_create_bar_chart_single_day(self):
        data = {"2026-04-25": 500.0}
        result = report_service._create_bar_chart(data, "Single Day")
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# Comparison logic tests
# ---------------------------------------------------------------------------


class TestComparison:
    """Test period-over-period comparison calculations."""

    def test_pct_change_increase(self):
        result = report_service._pct_change(150.0, 100.0)
        assert "50.0%" in result
        assert "more" in result.lower()

    def test_pct_change_decrease(self):
        result = report_service._pct_change(80.0, 100.0)
        assert "20.0%" in result
        assert "less" in result.lower()

    def test_pct_change_no_previous(self):
        result = report_service._pct_change(100.0, 0.0)
        assert "new" in result.lower() or result != ""

    def test_pct_change_same(self):
        result = report_service._pct_change(100.0, 100.0)
        assert "same" in result.lower()

    def test_pct_change_both_zero(self):
        result = report_service._pct_change(0.0, 0.0)
        assert result == ""

    def test_calculate_comparison(self):
        current = {"Food": 500.0, "Transport": 200.0}
        previous = {"Food": 400.0, "Coffee": 100.0}
        result = report_service._calculate_comparison(current, previous)
        assert "Food" in result
        assert "Transport" in result
        assert "Coffee" in result  # From previous period


# ---------------------------------------------------------------------------
# HTML report tests
# ---------------------------------------------------------------------------


class TestHtmlReport:
    """Test HTML report building."""

    def test_build_report_html(self):
        html = report_service._build_report_html(
            title="📊 Weekly Summary",
            total=2300.0,
            total_change="↑ 15% more",
            categories={"Food": 1200.0, "Transport": 800.0, "Coffee": 300.0},
            comparison={"Food": "↑ 20%", "Transport": "↓ 5%", "Coffee": "same"},
            period="week",
            prev_total=2000.0,
            attachments=[],
        )
        assert "Weekly Summary" in html
        assert "₹2,300.00" in html
        assert "Food" in html
        assert "Transport" in html

    def test_build_report_html_with_insights(self):
        html = report_service._build_report_html(
            title="📊 Monthly Summary",
            total=10000.0,
            total_change="",
            categories={"Groceries": 5000.0},
            comparison={},
            period="month",
            prev_total=0,
            attachments=[],
            extra_insights=["Your Groceries spending averaged ₹166.67/day"],
        )
        assert "Insights" in html
        assert "₹166.67/day" in html


# ---------------------------------------------------------------------------
# Weekly/Monthly report generation tests
# ---------------------------------------------------------------------------


class TestWeeklyReport:
    """Test full weekly report generation."""

    @pytest.mark.asyncio
    @patch("app.services.report_service.expense_service")
    async def test_weekly_report_full(self, mock_es, db: AsyncSession, test_user: User):
        mock_es.get_expenses_by_category = AsyncMock(
            return_value={"Food": 1000.0, "Transport": 500.0}
        )
        mock_es.get_daily_totals = AsyncMock(
            return_value={"2026-04-20": 300.0, "2026-04-21": 200.0}
        )
        mock_es.get_total = AsyncMock(return_value=1500.0)

        html, attachments = await report_service.generate_weekly_report(
            db, test_user.id
        )
        assert "Weekly Summary" in html or "Food" in html
        assert len(attachments) == 2  # pie + bar
        assert all(a[1][:4] == b"\x89PNG" for a in attachments)


class TestMonthlyReport:
    """Test full monthly report generation."""

    @pytest.mark.asyncio
    @patch("app.services.report_service.expense_service")
    async def test_monthly_report_full(self, mock_es, db: AsyncSession, test_user: User):
        mock_es.get_expenses_by_category = AsyncMock(
            return_value={"Groceries": 5000.0, "Utilities": 2000.0}
        )
        mock_es.get_daily_totals = AsyncMock(
            return_value={"2026-04-01": 500.0, "2026-04-02": 300.0}
        )
        mock_es.get_total = AsyncMock(return_value=7000.0)

        html, attachments = await report_service.generate_monthly_report(
            db, test_user.id
        )
        assert "Monthly" in html or "Groceries" in html
        assert len(attachments) == 2
