"""
Unit tests for AI service (Gemini expense parsing, receipt extraction, query interpretation).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.services.ai_service import (
    parse_expense_text,
    parse_receipt_image,
    interpret_query,
    generate_insights,
    _extract_json,
)
from app.exceptions.custom_exceptions import AIParsingError


# ---------------------------------------------------------------------------
# JSON extraction tests
# ---------------------------------------------------------------------------


class TestExtractJson:
    """Test the JSON extraction utility."""

    def test_extract_plain_json_array(self):
        text = '[{"amount": 50.0, "category": "Food"}]'
        result = _extract_json(text)
        assert isinstance(result, list)
        assert result[0]["amount"] == 50.0

    def test_extract_json_with_markdown_fences(self):
        text = '```json\n[{"amount": 100.0, "category": "Transport"}]\n```'
        result = _extract_json(text)
        assert isinstance(result, list)
        assert result[0]["category"] == "Transport"

    def test_extract_json_object(self):
        text = '{"amount": 200.0, "items": ["pizza"]}'
        result = _extract_json(text)
        assert isinstance(result, dict)
        assert result["amount"] == 200.0

    def test_extract_json_with_surrounding_text(self):
        text = 'Here is the result:\n[{"amount": 75.0, "category": "Coffee"}]\nDone.'
        result = _extract_json(text)
        assert isinstance(result, list)

    def test_extract_json_invalid_raises(self):
        with pytest.raises(AIParsingError):
            _extract_json("This is not JSON at all")

    def test_extract_json_empty_string_raises(self):
        with pytest.raises(AIParsingError):
            _extract_json("")


# ---------------------------------------------------------------------------
# Expense text parsing tests
# ---------------------------------------------------------------------------


class TestParseExpenseText:
    """Test Gemini-powered expense parsing."""

    @pytest.mark.asyncio
    @patch("app.services.ai_service._get_model")
    async def test_parse_single_expense(self, mock_get_model):
        mock_response = MagicMock()
        mock_response.text = json.dumps([
            {"amount": 200.0, "category": "Food", "description": "lunch", "date": "2026-04-25"}
        ])
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_get_model.return_value = mock_model

        result = await parse_expense_text("spent 200 on lunch")
        assert len(result) == 1
        assert result[0]["amount"] == 200.0
        assert result[0]["category"] == "Food"

    @pytest.mark.asyncio
    @patch("app.services.ai_service._get_model")
    async def test_parse_multiple_expenses(self, mock_get_model):
        mock_response = MagicMock()
        mock_response.text = json.dumps([
            {"amount": 50.0, "category": "Coffee", "description": "coffee", "date": "2026-04-25"},
            {"amount": 150.0, "category": "Transport", "description": "uber", "date": "2026-04-25"},
        ])
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_get_model.return_value = mock_model

        result = await parse_expense_text("50 coffee and 150 uber")
        assert len(result) == 2
        assert result[0]["amount"] == 50.0
        assert result[1]["amount"] == 150.0

    @pytest.mark.asyncio
    @patch("app.services.ai_service._get_model")
    async def test_parse_empty_response(self, mock_get_model):
        mock_response = MagicMock()
        mock_response.text = "[]"
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_get_model.return_value = mock_model

        result = await parse_expense_text("hello there")
        assert result == []

    @pytest.mark.asyncio
    @patch("app.services.ai_service._get_model")
    async def test_parse_single_dict_wraps_to_list(self, mock_get_model):
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {"amount": 100.0, "category": "Food", "description": "snack", "date": "2026-04-25"}
        )
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_get_model.return_value = mock_model

        result = await parse_expense_text("100 snack")
        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    @patch("app.services.ai_service._get_model")
    async def test_parse_malformed_response_raises(self, mock_get_model):
        mock_response = MagicMock()
        mock_response.text = "I don't understand"
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_get_model.return_value = mock_model

        with pytest.raises(AIParsingError):
            await parse_expense_text("random text")

    @pytest.mark.asyncio
    @patch("app.services.ai_service._get_model")
    async def test_parse_with_markdown_fences(self, mock_get_model):
        mock_response = MagicMock()
        mock_response.text = '```json\n[{"amount": 300.0, "category": "Shopping", "description": "shoes", "date": "2026-04-25"}]\n```'
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_get_model.return_value = mock_model

        result = await parse_expense_text("300 on shoes")
        assert len(result) == 1
        assert result[0]["category"] == "Shopping"


# ---------------------------------------------------------------------------
# Receipt image parsing tests
# ---------------------------------------------------------------------------


class TestParseReceiptImage:
    """Test Gemini Vision receipt extraction."""

    @pytest.mark.asyncio
    @patch("app.services.ai_service._get_model")
    async def test_parse_receipt_success(self, mock_get_model, sample_receipt_image):
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "amount": 540.0,
            "items": ["Biryani", "Naan"],
            "category": "Food",
            "confidence": 0.9,
        })
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_get_model.return_value = mock_model

        result = await parse_receipt_image(sample_receipt_image)
        assert result["amount"] == 540.0
        assert result["category"] == "Food"
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    @patch("app.services.ai_service._get_model")
    async def test_parse_receipt_defaults(self, mock_get_model, sample_receipt_image):
        mock_response = MagicMock()
        mock_response.text = json.dumps({"amount": 100.0})
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_get_model.return_value = mock_model

        result = await parse_receipt_image(sample_receipt_image)
        assert result["amount"] == 100.0
        assert result["items"] == []
        assert result["category"] == "Other"
        assert result["confidence"] == 0.5

    @pytest.mark.asyncio
    @patch("app.services.ai_service._get_model")
    async def test_parse_receipt_missing_amount_raises(self, mock_get_model, sample_receipt_image):
        mock_response = MagicMock()
        mock_response.text = json.dumps({"items": ["something"], "category": "Food"})
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_get_model.return_value = mock_model

        with pytest.raises(AIParsingError):
            await parse_receipt_image(sample_receipt_image)


# ---------------------------------------------------------------------------
# Query interpretation tests
# ---------------------------------------------------------------------------


class TestInterpretQuery:
    """Test natural language query interpretation."""

    @pytest.mark.asyncio
    @patch("app.services.ai_service._get_model")
    async def test_interpret_category_query(self, mock_get_model):
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "type": "category_date",
            "start_date": None,
            "end_date": None,
            "category": "Food",
            "period": "week",
        })
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_get_model.return_value = mock_model

        result = await interpret_query("How much on food this week?")
        assert result["category"] == "Food"
        assert result["period"] == "week"

    @pytest.mark.asyncio
    @patch("app.services.ai_service._get_model")
    async def test_interpret_date_query(self, mock_get_model):
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "type": "date_range",
            "start_date": "2026-04-24",
            "end_date": "2026-04-24",
            "category": None,
            "period": "yesterday",
        })
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_get_model.return_value = mock_model

        result = await interpret_query("What did I spend yesterday?")
        assert result["period"] == "yesterday"


# ---------------------------------------------------------------------------
# Insights tests
# ---------------------------------------------------------------------------


class TestGenerateInsights:
    """Test spending insight generation."""

    @pytest.mark.asyncio
    @patch("app.services.ai_service._get_model")
    async def test_generate_insights_success(self, mock_get_model):
        mock_response = MagicMock()
        mock_response.text = "Your food spending increased 20% this week."
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_get_model.return_value = mock_model

        result = await generate_insights({"Food": 500}, {"Food": 400})
        assert "food" in result.lower() or "20%" in result

    @pytest.mark.asyncio
    @patch("app.services.ai_service._get_model")
    async def test_generate_insights_failure_returns_empty(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(side_effect=Exception("API error"))
        mock_get_model.return_value = mock_model

        result = await generate_insights({"Food": 500})
        assert result == ""
