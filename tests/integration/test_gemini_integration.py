"""
Integration tests for Gemini API.
These tests call the actual Gemini API and are skipped unless --run-integration is passed.
"""

import os
import pytest

from app.exceptions.custom_exceptions import AIParsingError


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def check_api_key():
    """Skip if no real Gemini API key is set."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key or key.startswith("test_"):
        pytest.skip("Real GEMINI_API_KEY not set")


class TestGeminiExpenseParsing:
    """Test actual Gemini API expense parsing."""

    @pytest.mark.asyncio
    async def test_parse_simple_expense(self):
        from app.services.ai_service import parse_expense_text

        result = await parse_expense_text("spent 200 on lunch")
        assert len(result) >= 1
        assert result[0]["amount"] > 0
        assert result[0]["category"]

    @pytest.mark.asyncio
    async def test_parse_multiple_expenses(self):
        from app.services.ai_service import parse_expense_text

        result = await parse_expense_text("50 coffee and 300 uber yesterday")
        assert len(result) >= 2

    @pytest.mark.asyncio
    async def test_parse_informal_language(self):
        from app.services.ai_service import parse_expense_text

        result = await parse_expense_text("had a 500 rupee dinner at the restaurant")
        assert len(result) >= 1
        assert result[0]["amount"] >= 400  # Approximate


class TestGeminiQueryInterpretation:
    """Test actual Gemini API query interpretation."""

    @pytest.mark.asyncio
    async def test_interpret_food_query(self):
        from app.services.ai_service import interpret_query

        result = await interpret_query("How much did I spend on food this week?")
        assert result.get("category") is not None or result.get("period") is not None

    @pytest.mark.asyncio
    async def test_interpret_date_query(self):
        from app.services.ai_service import interpret_query

        result = await interpret_query("Show yesterday's expenses")
        assert result.get("period") is not None or result.get("start_date") is not None


class TestGeminiVision:
    """Test Gemini Vision API with a test image."""

    @pytest.mark.asyncio
    async def test_vision_with_blank_image(self, sample_receipt_image):
        """A blank image should either return low confidence or raise."""
        from app.services.ai_service import parse_receipt_image

        try:
            result = await parse_receipt_image(sample_receipt_image)
            # Blank image — amount should be 0 or very low confidence
            assert result.get("confidence", 0) <= 0.5 or result.get("amount", 0) == 0
        except AIParsingError:
            pass  # Acceptable — blank image is not a receipt
