"""
Unit tests for validators and helpers.
"""

import pytest
from datetime import datetime

from app.utils.validators import validate_expense, sanitize_category, validate_telegram_update
from app.utils.helpers import format_currency, format_expense_confirmation, format_receipt_confirmation, get_date_range, format_report_header, parse_date_string


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------


class TestSanitizeCategory:
    """Test category normalization."""

    def test_title_case(self):
        assert sanitize_category("food") == "Food"

    def test_alias_uber(self):
        assert sanitize_category("uber") == "Transport"

    def test_alias_chai(self):
        assert sanitize_category("chai") == "Coffee"

    def test_alias_medicine(self):
        assert sanitize_category("medicine") == "Medical"

    def test_alias_netflix(self):
        assert sanitize_category("netflix") == "Subscriptions"

    def test_alias_electricity(self):
        assert sanitize_category("electricity") == "Utilities"

    def test_empty_returns_other(self):
        assert sanitize_category("") == "Other"

    def test_whitespace_stripped(self):
        assert sanitize_category("  food  ") == "Food"

    def test_unknown_category_title_cased(self):
        assert sanitize_category("random stuff") == "Random Stuff"


class TestValidateExpense:
    """Test expense validation."""

    def test_valid_basic(self):
        result = validate_expense({"amount": 100, "category": "Food"})
        assert result["amount"] == 100.0
        assert result["category"] == "Food"

    def test_valid_with_date(self):
        result = validate_expense({
            "amount": 50.5, "category": "Coffee", "date": "2026-04-20"
        })
        assert result["date"] == "2026-04-20"
        assert result["amount"] == 50.5

    def test_valid_with_description(self):
        result = validate_expense({
            "amount": 200, "category": "Food", "description": "lunch"
        })
        assert result["description"] == "lunch"

    def test_rounds_amount(self):
        result = validate_expense({"amount": 99.999, "category": "Food"})
        assert result["amount"] == 100.0

    def test_invalid_zero_amount(self):
        with pytest.raises(ValueError, match="greater than zero"):
            validate_expense({"amount": 0, "category": "Food"})

    def test_invalid_negative_amount(self):
        with pytest.raises(ValueError, match="greater than zero"):
            validate_expense({"amount": -50, "category": "Food"})

    def test_invalid_missing_amount(self):
        with pytest.raises(ValueError, match="required"):
            validate_expense({"category": "Food"})

    def test_invalid_missing_category(self):
        with pytest.raises(ValueError, match="required"):
            validate_expense({"amount": 100, "category": ""})

    def test_invalid_too_large_amount(self):
        with pytest.raises(ValueError, match="unreasonably large"):
            validate_expense({"amount": 50_000_000, "category": "Food"})

    def test_invalid_non_numeric_amount(self):
        with pytest.raises(ValueError, match="Invalid amount"):
            validate_expense({"amount": "not_a_number", "category": "Food"})

    def test_invalid_date_ignored(self):
        result = validate_expense({
            "amount": 100, "category": "Food", "date": "invalid-date"
        })
        assert result["date"] is None

    def test_no_description_defaults_none(self):
        result = validate_expense({"amount": 100, "category": "Food"})
        assert result["description"] is None

    def test_empty_description_defaults_none(self):
        result = validate_expense({
            "amount": 100, "category": "Food", "description": "  "
        })
        assert result["description"] is None

    def test_category_normalized(self):
        result = validate_expense({"amount": 100, "category": "uber"})
        assert result["category"] == "Transport"


class TestValidateTelegramUpdate:
    """Test Telegram update validation."""

    def test_valid_message_update(self, mock_telegram_text_update):
        assert validate_telegram_update(mock_telegram_text_update) is True

    def test_valid_command_update(self, mock_telegram_command_update):
        assert validate_telegram_update(mock_telegram_command_update) is True

    def test_invalid_no_update_id(self):
        assert validate_telegram_update({"message": {}}) is False

    def test_invalid_no_message(self):
        assert validate_telegram_update({"update_id": 1}) is False

    def test_invalid_not_dict(self):
        assert validate_telegram_update("not a dict") is False

    def test_invalid_none(self):
        assert validate_telegram_update(None) is False


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestFormatCurrency:
    """Test currency formatting."""

    def test_simple_amount(self):
        assert format_currency(100) == "₹100.00"

    def test_decimal_amount(self):
        assert format_currency(99.50) == "₹99.50"

    def test_large_amount_with_commas(self):
        assert format_currency(12345.67) == "₹12,345.67"

    def test_zero(self):
        assert format_currency(0) == "₹0.00"


class TestFormatExpenseConfirmation:
    """Test expense confirmation message formatting."""

    def test_single_expense(self):
        msg = format_expense_confirmation([{"amount": 100, "category": "Food"}])
        assert "✅" in msg
        assert "₹100.00" in msg
        assert "Food" in msg

    def test_multiple_expenses(self):
        expenses = [
            {"amount": 200, "category": "Food"},
            {"amount": 50, "category": "Transport"},
        ]
        msg = format_expense_confirmation(expenses)
        assert "2 expenses" in msg
        assert "₹200.00" in msg
        assert "₹50.00" in msg

    def test_empty_list(self):
        msg = format_expense_confirmation([])
        assert "No expenses" in msg


class TestFormatReceiptConfirmation:
    """Test receipt confirmation formatting."""

    def test_with_items(self):
        data = {"amount": 540, "category": "Food", "items": ["Biryani", "Naan"]}
        msg = format_receipt_confirmation(data)
        assert "₹540.00" in msg
        assert "Food" in msg
        assert "Biryani" in msg
        assert "Yes or No" in msg

    def test_without_items(self):
        data = {"amount": 200, "category": "Shopping"}
        msg = format_receipt_confirmation(data)
        assert "₹200.00" in msg
        assert "Yes or No" in msg


class TestGetDateRange:
    """Test date range calculation."""

    def test_today_range(self):
        start, end = get_date_range("today")
        assert start.hour == 0
        assert start.minute == 0
        assert end.hour == 23

    def test_yesterday_range(self):
        from datetime import timedelta
        start, end = get_date_range("yesterday")
        today_start, _ = get_date_range("today")
        assert start < today_start

    def test_week_range(self):
        start, end = get_date_range("week")
        # Start should be Monday
        assert start.weekday() == 0

    def test_month_range(self):
        start, end = get_date_range("month")
        assert start.day == 1

    def test_unknown_period_raises(self):
        with pytest.raises(ValueError):
            get_date_range("invalid_period")


class TestFormatReportHeader:
    """Test report header formatting."""

    def test_today_header(self):
        start, end = get_date_range("today")
        header = format_report_header("today", start, end)
        assert "📊" in header
        assert "Today" in header

    def test_week_header(self):
        start, end = get_date_range("week")
        header = format_report_header("week", start, end)
        assert "Weekly" in header

    def test_month_header(self):
        start, end = get_date_range("month")
        header = format_report_header("month", start, end)
        assert "Monthly" in header
