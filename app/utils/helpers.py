"""
Formatting helpers, date utilities, and currency functions.
"""

from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo

from app.config import get_settings


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------

CURRENCY_SYMBOL = "₹"


def format_currency(amount: float) -> str:
    """Format amount with ₹ symbol and 2 decimal places."""
    return f"{CURRENCY_SYMBOL}{amount:,.2f}"


# ---------------------------------------------------------------------------
# Expense confirmation messages
# ---------------------------------------------------------------------------


def format_expense_confirmation(expenses: list[dict]) -> str:
    """
    Build a user-friendly confirmation message.

    Single:  "✅ Added ₹100.00 (Food)"
    Multi:   "✅ Added 2 expenses:\n₹200.00 (Food)\n₹50.00 (Transport)"
    """
    if not expenses:
        return "No expenses to confirm."

    if len(expenses) == 1:
        e = expenses[0]
        return f"✅ Added {format_currency(e['amount'])} ({e['category']})"

    lines = [f"✅ Added {len(expenses)} expenses:"]
    for e in expenses:
        lines.append(f"  {format_currency(e['amount'])} ({e['category']})")
    return "\n".join(lines)


def format_receipt_confirmation(data: dict) -> str:
    """Ask user to confirm parsed receipt data."""
    amount = format_currency(data.get("amount", 0))
    category = data.get("category", "Unknown")
    items = data.get("items", [])

    msg = f"🧾 Detected {amount} ({category})."
    if items:
        msg += "\nItems: " + ", ".join(items[:5])
        if len(items) > 5:
            msg += f" (+{len(items) - 5} more)"
    msg += "\n\nConfirm? Reply Yes or No"
    return msg


# ---------------------------------------------------------------------------
# Date utilities
# ---------------------------------------------------------------------------


def get_user_timezone() -> ZoneInfo:
    """Return the configured timezone."""
    settings = get_settings()
    return ZoneInfo(settings.REPORT_TIMEZONE)


def now_local() -> datetime:
    """Current datetime in configured timezone."""
    return datetime.now(get_user_timezone())


def today_local() -> datetime:
    """Start of today in configured timezone (midnight)."""
    tz = get_user_timezone()
    local_now = datetime.now(tz)
    return datetime.combine(local_now.date(), time.min, tzinfo=tz)


def get_date_range(period: str) -> tuple[datetime, datetime]:
    """
    Return (start, end) datetimes for a named period.

    Supported periods: 'today', 'yesterday', 'week', 'month', 'last_week', 'last_month'
    """
    tz = get_user_timezone()
    local_now = datetime.now(tz)
    today_start = datetime.combine(local_now.date(), time.min, tzinfo=tz)
    today_end = datetime.combine(local_now.date(), time.max, tzinfo=tz)

    match period.lower():
        case "today":
            return today_start, today_end

        case "yesterday":
            yesterday = today_start - timedelta(days=1)
            return yesterday, datetime.combine(
                yesterday.date(), time.max, tzinfo=tz
            )

        case "week":
            # Monday-based week
            weekday = local_now.weekday()  # Mon=0
            start = today_start - timedelta(days=weekday)
            return start, today_end

        case "last_week":
            weekday = local_now.weekday()
            this_monday = today_start - timedelta(days=weekday)
            last_monday = this_monday - timedelta(days=7)
            last_sunday = this_monday - timedelta(seconds=1)
            return last_monday, last_sunday

        case "month":
            start = today_start.replace(day=1)
            return start, today_end

        case "last_month":
            first_this_month = today_start.replace(day=1)
            last_day_prev = first_this_month - timedelta(days=1)
            first_prev_month = last_day_prev.replace(day=1)
            return (
                datetime.combine(first_prev_month.date(), time.min, tzinfo=tz),
                datetime.combine(last_day_prev.date(), time.max, tzinfo=tz),
            )

        case _:
            raise ValueError(f"Unknown period: {period}")


def format_report_header(period: str, start: datetime, end: datetime) -> str:
    """Generate a report header like '📊 Weekly Summary (Jan 8-14)'."""
    if period == "today":
        date_str = start.strftime("%b %d, %Y")
        return f"📊 Today's Summary ({date_str})"
    elif period in ("week", "last_week"):
        s = start.strftime("%b %d")
        e = end.strftime("%d")
        return f"📊 Weekly Summary ({s}-{e})"
    elif period in ("month", "last_month"):
        s = start.strftime("%b %Y")
        return f"📊 Monthly Summary ({s})"
    else:
        s = start.strftime("%b %d")
        e = end.strftime("%b %d")
        return f"📊 Summary ({s} - {e})"


def parse_date_string(date_str: str) -> datetime:
    """Parse a YYYY-MM-DD string into a timezone-aware datetime."""
    tz = get_user_timezone()
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.replace(tzinfo=tz)
