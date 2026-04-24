"""
Input validation utilities for expenses and Telegram updates.
"""

from datetime import datetime
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Valid categories (for normalization — AI may suggest others, which is fine)
KNOWN_CATEGORIES = {
    "food", "transport", "transportation", "groceries", "shopping",
    "entertainment", "health", "medical", "utilities", "rent",
    "education", "travel", "clothing", "electronics", "subscriptions",
    "personal", "gifts", "donations", "insurance", "fuel",
    "coffee", "restaurant", "snacks", "household", "other",
}

# Category normalization map
CATEGORY_ALIASES = {
    "transportation": "Transport",
    "cab": "Transport",
    "uber": "Transport",
    "ola": "Transport",
    "auto": "Transport",
    "bus": "Transport",
    "train": "Transport",
    "metro": "Transport",
    "taxi": "Transport",
    "petrol": "Fuel",
    "diesel": "Fuel",
    "gas": "Fuel",
    "breakfast": "Food",
    "lunch": "Food",
    "dinner": "Food",
    "snack": "Snacks",
    "tea": "Coffee",
    "chai": "Coffee",
    "medicine": "Medical",
    "doctor": "Medical",
    "hospital": "Medical",
    "gym": "Health",
    "movie": "Entertainment",
    "netflix": "Subscriptions",
    "spotify": "Subscriptions",
    "electricity": "Utilities",
    "water": "Utilities",
    "internet": "Utilities",
    "wifi": "Utilities",
    "phone": "Utilities",
    "mobile": "Utilities",
}


def sanitize_category(category: str) -> str:
    """
    Normalize category name:
    - Strip whitespace
    - Map aliases to canonical names
    - Title-case the result
    """
    if not category:
        return "Other"

    cleaned = category.strip().lower()

    # Check alias map first
    if cleaned in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[cleaned]

    # Title-case for display
    return cleaned.title()


def validate_expense(data: dict) -> dict:
    """
    Validate and normalize a parsed expense dict.

    Required keys: amount, category
    Optional: description, date

    Returns validated dict or raises ValueError.
    """
    errors = []

    # Amount
    amount = data.get("amount")
    if amount is None:
        errors.append("Amount is required.")
    else:
        try:
            amount = float(amount)
            if amount <= 0:
                errors.append("Amount must be greater than zero.")
            if amount > 10_000_000:
                errors.append("Amount seems unreasonably large. Please check.")
        except (ValueError, TypeError):
            errors.append(f"Invalid amount: {amount}")

    # Category
    category = data.get("category", "")
    if not category or not category.strip():
        errors.append("Category is required.")

    if errors:
        raise ValueError("; ".join(errors))

    # Normalize
    validated = {
        "amount": round(float(amount), 2),
        "category": sanitize_category(category),
        "description": str(data.get("description", "")).strip() or None,
    }

    # Date (optional — caller will default to today)
    date_val = data.get("date")
    if date_val:
        if isinstance(date_val, str):
            try:
                validated["date"] = datetime.strptime(date_val, "%Y-%m-%d").date().isoformat()
            except ValueError:
                logger.warning(f"Invalid date format: {date_val}, ignoring")
                validated["date"] = None
        elif isinstance(date_val, datetime):
            validated["date"] = date_val.date().isoformat()
        else:
            validated["date"] = None
    else:
        validated["date"] = None

    return validated


def validate_telegram_update(data: dict) -> bool:
    """
    Basic validation that a Telegram update payload has required fields.
    Returns True if valid, False otherwise.
    """
    if not isinstance(data, dict):
        return False

    # Must have update_id
    if "update_id" not in data:
        return False

    # Must have at least one of: message, edited_message, callback_query
    if not any(key in data for key in ("message", "edited_message", "callback_query")):
        return False

    return True
