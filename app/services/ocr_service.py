"""
OCR service for receipt processing.
Primary: Gemini Vision API
Fallback: Tesseract OCR
"""

import io
import re

from app.services.ai_service import parse_receipt_image
from app.exceptions.custom_exceptions import OCRError
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def process_receipt(image_bytes: bytes) -> dict:
    """
    Process a receipt image. Try Gemini Vision first, fall back to Tesseract.

    Returns:
        dict with keys: amount, items, category, confidence
    """
    # Primary: Gemini Vision
    try:
        result = await parse_receipt_image(image_bytes)
        if result and result.get("amount", 0) > 0:
            logger.info("Receipt processed via Gemini Vision")
            return result
    except Exception as e:
        logger.warning(f"Gemini Vision failed, trying Tesseract fallback: {e}")

    # Fallback: Tesseract
    try:
        result = _tesseract_extract(image_bytes)
        if result and result.get("amount", 0) > 0:
            logger.info("Receipt processed via Tesseract fallback")
            return result
    except Exception as e:
        logger.error(f"Tesseract fallback also failed: {e}")

    raise OCRError("Could not extract data from receipt image using any method")


def _tesseract_extract(image_bytes: bytes) -> dict:
    """
    Tesseract OCR fallback — extract text and parse amounts with regex.
    """
    try:
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(image)
        logger.debug(f"Tesseract raw text: {text[:300]}")

        return _parse_receipt_text(text)

    except ImportError:
        logger.warning("pytesseract not installed — Tesseract fallback unavailable")
        raise OCRError("Tesseract OCR is not available on this system")
    except Exception as e:
        logger.error(f"Tesseract extraction error: {e}")
        raise OCRError(f"Tesseract failed: {e}")


def _parse_receipt_text(text: str) -> dict:
    """
    Parse OCR text to extract total amount using common receipt patterns.
    """
    lines = text.strip().split("\n")
    amounts = []
    items = []

    # Pattern: Find amounts with currency symbols or 'total' keywords
    amount_pattern = re.compile(
        r"(?:(?:total|amount|grand\s*total|net\s*total|balance\s*due|₹|rs\.?|inr)\s*[:\s]*)"
        r"(\d[\d,]*(?:\.\d{1,2})?)",
        re.IGNORECASE,
    )

    # Generic number pattern for fallback
    number_pattern = re.compile(r"(\d[\d,]*(?:\.\d{1,2})?)")

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # Check for total-like lines
        match = amount_pattern.search(line_clean)
        if match:
            amount_str = match.group(1).replace(",", "")
            try:
                amounts.append(float(amount_str))
            except ValueError:
                pass
        elif line_clean and len(line_clean) > 3:
            items.append(line_clean[:50])

    # Take the largest amount as the total (usually the grand total)
    total = max(amounts) if amounts else 0.0

    return {
        "amount": total,
        "items": items[:10],  # Cap items list
        "category": "Other",  # Tesseract can't reliably categorize
        "confidence": 0.3,    # Low confidence for OCR fallback
    }
