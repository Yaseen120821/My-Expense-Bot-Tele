"""
Unit tests for OCR service (receipt processing with Gemini Vision + Tesseract fallback).
"""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.ocr_service import process_receipt, _parse_receipt_text
from app.exceptions.custom_exceptions import OCRError


# ---------------------------------------------------------------------------
# Receipt text parsing (Tesseract output)
# ---------------------------------------------------------------------------


class TestParseReceiptText:
    """Test regex-based receipt text parsing."""

    def test_parse_total_amount(self):
        text = """
        RESTAURANT XYZ
        Chicken Biryani  200
        Naan              40
        Cold Drink        50
        =====================
        Total: 290
        """
        result = _parse_receipt_text(text)
        assert result["amount"] == 290.0

    def test_parse_grand_total(self):
        text = """
        Subtotal: 500
        Tax: 25
        Grand Total: 525
        """
        result = _parse_receipt_text(text)
        assert result["amount"] == 525.0

    def test_parse_rupee_symbol(self):
        text = "Amount: ₹ 1200.50"
        result = _parse_receipt_text(text)
        assert result["amount"] == 1200.50

    def test_parse_rs_prefix(self):
        text = "Total Rs. 340"
        result = _parse_receipt_text(text)
        assert result["amount"] == 340.0

    def test_parse_no_amount(self):
        text = "Thank you for visiting"
        result = _parse_receipt_text(text)
        assert result["amount"] == 0.0

    def test_parse_multiple_amounts_takes_largest(self):
        text = """
        Item 1: Rs 100
        Item 2: Rs 200
        Total: Rs 300
        """
        result = _parse_receipt_text(text)
        assert result["amount"] == 300.0

    def test_parse_items_extracted(self):
        text = """
        Coffee          120
        Sandwich        180
        Total: 300
        """
        result = _parse_receipt_text(text)
        assert len(result["items"]) > 0

    def test_parse_default_category(self):
        result = _parse_receipt_text("Total: 500")
        assert result["category"] == "Other"

    def test_parse_low_confidence(self):
        result = _parse_receipt_text("Total: 500")
        assert result["confidence"] == 0.3


# ---------------------------------------------------------------------------
# Receipt processing pipeline
# ---------------------------------------------------------------------------


class TestProcessReceipt:
    """Test the combined OCR pipeline."""

    @pytest.mark.asyncio
    @patch("app.services.ocr_service.parse_receipt_image")
    async def test_gemini_vision_success(self, mock_vision, sample_receipt_image):
        mock_vision.return_value = {
            "amount": 540.0,
            "items": ["Biryani", "Naan"],
            "category": "Food",
            "confidence": 0.95,
        }

        result = await process_receipt(sample_receipt_image)
        assert result["amount"] == 540.0
        assert result["category"] == "Food"
        mock_vision.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.ocr_service._tesseract_extract")
    @patch("app.services.ocr_service.parse_receipt_image")
    async def test_gemini_fails_tesseract_fallback(
        self, mock_vision, mock_tesseract, sample_receipt_image
    ):
        mock_vision.side_effect = Exception("Vision API failed")
        mock_tesseract.return_value = {
            "amount": 300.0,
            "items": [],
            "category": "Other",
            "confidence": 0.3,
        }

        result = await process_receipt(sample_receipt_image)
        assert result["amount"] == 300.0
        mock_tesseract.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.ocr_service._tesseract_extract")
    @patch("app.services.ocr_service.parse_receipt_image")
    async def test_both_fail_raises_ocr_error(
        self, mock_vision, mock_tesseract, sample_receipt_image
    ):
        mock_vision.side_effect = Exception("Vision failed")
        mock_tesseract.side_effect = Exception("Tesseract failed")

        with pytest.raises(OCRError):
            await process_receipt(sample_receipt_image)

    @pytest.mark.asyncio
    @patch("app.services.ocr_service.parse_receipt_image")
    async def test_gemini_zero_amount_triggers_fallback(
        self, mock_vision, sample_receipt_image
    ):
        mock_vision.return_value = {"amount": 0, "items": [], "category": "Other", "confidence": 0.1}

        # Without tesseract installed, this will raise OCRError
        with pytest.raises(OCRError):
            await process_receipt(sample_receipt_image)
