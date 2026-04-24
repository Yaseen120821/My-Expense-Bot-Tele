"""
Google Gemini AI service for expense parsing, receipt extraction, and query interpretation.
"""

import json
import re
from datetime import datetime

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import get_settings
from app.exceptions.custom_exceptions import AIParsingError
from app.utils.logger import get_logger
from app.utils.helpers import now_local

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Gemini client initialization
# ---------------------------------------------------------------------------

_model = None
_configured = False


def _ensure_configured() -> None:
    global _configured
    if not _configured:
        settings = get_settings()
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


def _get_model():
    global _model
    if _model is None:
        _ensure_configured()
        settings = get_settings()
        _model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=2048,
            ),
        )
    return _model


def _extract_json(text: str) -> list | dict:
    """Extract JSON from model response, handling markdown code blocks."""
    # Remove markdown code block fences
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        parsed = json.loads(text)
        return parsed
    except json.JSONDecodeError as e:
        # Try to find JSON within the text
        json_match = re.search(r'[\[\{].*[\]\}]', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        raise AIParsingError(
            message=f"Failed to parse JSON from AI response: {e}",
            raw_response=text,
        )


# ---------------------------------------------------------------------------
# Expense Text Parsing
# ---------------------------------------------------------------------------

EXPENSE_PARSE_PROMPT = """You are an expense parser. Extract expense(s) from the user's message.

RULES:
1. Return ONLY a valid JSON array of expense objects. No explanation, no markdown.
2. Each object must have exactly these fields:
   - "amount": number (always positive, e.g. 50.0)
   - "category": string (e.g. "Food", "Transport", "Shopping", "Coffee", "Groceries", etc.)
   - "description": string (brief description of what was purchased)
   - "date": string in "YYYY-MM-DD" format
3. Today's date is {today}.
4. If the user says "yesterday", use {yesterday}. Interpret relative dates accordingly.
5. If no date is mentioned, use today's date.
6. If category is ambiguous, infer from context (e.g., "coffee" → "Coffee", "uber" → "Transport").
7. If a single message contains multiple expenses, return multiple objects in the array.
8. Currency symbols (₹, $, etc.) should be stripped from amounts.
9. If you cannot parse any expense, return an empty array: []

EXAMPLES:
User: "spent 200 on lunch"
Output: [{{"amount": 200.0, "category": "Food", "description": "lunch", "date": "{today}"}}]

User: "50 coffee and 150 uber yesterday"
Output: [{{"amount": 50.0, "category": "Coffee", "description": "coffee", "date": "{yesterday}"}}, {{"amount": 150.0, "category": "Transport", "description": "uber", "date": "{yesterday}"}}]

User: "₹1200 groceries from BigBasket"
Output: [{{"amount": 1200.0, "category": "Groceries", "description": "groceries from BigBasket", "date": "{today}"}}]

Now parse the following message:
"""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def parse_expense_text(text: str) -> list[dict]:
    """
    Send user text to Gemini for structured expense parsing.
    Returns a list of expense dicts with: amount, category, description, date.
    """
    local_now = now_local()
    today_str = local_now.strftime("%Y-%m-%d")
    yesterday_str = (local_now - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")

    prompt = EXPENSE_PARSE_PROMPT.format(today=today_str, yesterday=yesterday_str)
    full_prompt = prompt + text

    logger.info(f"Parsing expense text: '{text[:100]}'")

    try:
        model = _get_model()
        response = await model.generate_content_async(full_prompt)
        raw = response.text
        logger.debug(f"Gemini raw response: {raw[:200]}")

        result = _extract_json(raw)

        # Ensure it's a list
        if isinstance(result, dict):
            result = [result]
        if not isinstance(result, list):
            raise AIParsingError("Expected JSON array", raw_response=raw)

        logger.info(f"Parsed {len(result)} expense(s) from text")
        return result

    except AIParsingError:
        raise
    except Exception as e:
        logger.error(f"Gemini API error during expense parsing: {e}")
        raise AIParsingError(
            message=f"AI parsing failed: {e}",
            raw_response=str(e),
        )


# ---------------------------------------------------------------------------
# Receipt Image Extraction (Gemini Vision)
# ---------------------------------------------------------------------------

RECEIPT_PARSE_PROMPT = """You are a receipt parser. Analyze this receipt image and extract:

Return ONLY valid JSON (no markdown, no explanation):
{{
    "amount": <total amount as number>,
    "items": [<list of item descriptions as strings>],
    "category": "<inferred category: Food, Groceries, Shopping, Medical, etc.>",
    "confidence": <0.0 to 1.0 how confident you are>
}}

RULES:
1. "amount" should be the TOTAL amount on the receipt.
2. If you can identify individual items, list them in "items".
3. Infer the category from the store name and items.
4. If the receipt is unclear, do your best and set confidence low.
5. Currency: assume ₹ (INR) unless clearly stated otherwise.
"""


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def parse_receipt_image(image_bytes: bytes) -> dict:
    """
    Send receipt image to Gemini Vision for extraction.
    Returns dict with: amount, items, category, confidence.
    """
    import PIL.Image
    import io

    logger.info(f"Parsing receipt image ({len(image_bytes)} bytes)")

    try:
        image = PIL.Image.open(io.BytesIO(image_bytes))
        model = _get_model()
        response = await model.generate_content_async([RECEIPT_PARSE_PROMPT, image])
        raw = response.text
        logger.debug(f"Gemini Vision raw response: {raw[:200]}")

        result = _extract_json(raw)
        if isinstance(result, list) and len(result) > 0:
            result = result[0]
        if not isinstance(result, dict):
            raise AIParsingError("Expected JSON object for receipt", raw_response=raw)

        # Validate required fields
        if "amount" not in result:
            raise AIParsingError("Receipt parse missing 'amount'", raw_response=raw)

        result.setdefault("items", [])
        result.setdefault("category", "Other")
        result.setdefault("confidence", 0.5)

        logger.info(f"Receipt parsed: ₹{result['amount']} ({result['category']})")
        return result

    except AIParsingError:
        raise
    except Exception as e:
        logger.error(f"Gemini Vision error: {e}")
        raise AIParsingError(
            message=f"Receipt parsing failed: {e}",
            raw_response=str(e),
        )


# ---------------------------------------------------------------------------
# Natural Language Query Interpretation
# ---------------------------------------------------------------------------

QUERY_INTERPRET_PROMPT = """You are a query interpreter for an expense tracking app.
The user is asking about their expenses. Parse their query into structured parameters.

Return ONLY valid JSON (no markdown):
{{
    "type": "<one of: date_range, category_filter, category_date, summary, specific_date>",
    "start_date": "<YYYY-MM-DD or null>",
    "end_date": "<YYYY-MM-DD or null>",
    "category": "<category name or null>",
    "period": "<today, yesterday, week, last_week, month, last_month, or null>"
}}

Today's date is {today}.

EXAMPLES:
"How much did I spend on food this week?" → {{"type": "category_date", "start_date": null, "end_date": null, "category": "Food", "period": "week"}}
"Show expenses for Monday" → {{"type": "specific_date", "start_date": "{monday}", "end_date": "{monday}", "category": null, "period": null}}
"What did I spend yesterday?" → {{"type": "date_range", "start_date": "{yesterday}", "end_date": "{yesterday}", "category": null, "period": "yesterday"}}
"Monthly summary" → {{"type": "summary", "start_date": null, "end_date": null, "category": null, "period": "month"}}

Now interpret:
"""


async def interpret_query(text: str) -> dict:
    """
    Use Gemini to interpret a natural language query about expenses.
    Returns structured query parameters.
    """
    local_now = now_local()
    today_str = local_now.strftime("%Y-%m-%d")
    yesterday_str = (local_now - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")

    # Calculate last Monday
    days_since_monday = local_now.weekday()
    monday = local_now - __import__("datetime").timedelta(days=days_since_monday)
    monday_str = monday.strftime("%Y-%m-%d")

    prompt = QUERY_INTERPRET_PROMPT.format(
        today=today_str,
        yesterday=yesterday_str,
        monday=monday_str,
    )
    full_prompt = prompt + text

    logger.info(f"Interpreting query: '{text[:100]}'")

    try:
        model = _get_model()
        response = await model.generate_content_async(full_prompt)
        raw = response.text
        result = _extract_json(raw)

        if isinstance(result, list):
            result = result[0] if result else {}

        logger.info(f"Query interpreted: {result}")
        return result

    except Exception as e:
        logger.error(f"Query interpretation failed: {e}")
        raise AIParsingError(
            message=f"Query interpretation failed: {e}",
            raw_response=str(e),
        )


# ---------------------------------------------------------------------------
# Spending Insights
# ---------------------------------------------------------------------------

INSIGHTS_PROMPT = """Analyze these expense records and provide 1-2 brief spending insights.
Be conversational and helpful. Use ₹ for currency.

Expense data:
{data}

Current period: {period}
Previous period comparison data (if available): {comparison}

Return 1-2 short insight sentences. No JSON, just plain text.
Example: "Your food spending increased 30% this week compared to last week."
"""


async def generate_insights(
    current_data: dict,
    comparison_data: dict | None = None,
    period: str = "week",
) -> str:
    """Generate AI-powered spending insights."""
    try:
        prompt = INSIGHTS_PROMPT.format(
            data=json.dumps(current_data, indent=2),
            period=period,
            comparison=json.dumps(comparison_data, indent=2) if comparison_data else "Not available",
        )

        model = _get_model()
        response = await model.generate_content_async(prompt)
        return response.text.strip()

    except Exception as e:
        logger.warning(f"Insight generation failed (non-critical): {e}")
        return ""
