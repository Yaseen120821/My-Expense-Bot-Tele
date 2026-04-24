"""
Interactive query service — converts natural language questions to database queries.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import ai_service, expense_service
from app.exceptions.custom_exceptions import QueryError
from app.utils.helpers import (
    format_currency,
    get_date_range,
    format_report_header,
    parse_date_string,
    now_local,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def handle_query(db: AsyncSession, user_id, text: str) -> str:
    """
    Process a natural language query:
    1. Interpret via Gemini → structured params
    2. Execute DB queries
    3. Format conversational response
    """
    try:
        # Step 1: Interpret query with AI
        params = await ai_service.interpret_query(text)
        logger.info(f"Query params: {params}")

        # Step 2: Resolve date range
        start_date = None
        end_date = None

        period = params.get("period")
        if period:
            try:
                start_date, end_date = get_date_range(period)
            except ValueError:
                pass

        # Override with explicit dates if provided
        if params.get("start_date"):
            start_date = parse_date_string(params["start_date"])
        if params.get("end_date"):
            from datetime import time
            end_date = parse_date_string(params["end_date"])
            end_date = end_date.replace(hour=23, minute=59, second=59)

        # Default to today if no dates resolved
        if not start_date or not end_date:
            start_date, end_date = get_date_range("today")

        category = params.get("category")

        # Step 3: Query database
        query_type = params.get("type", "date_range")

        if query_type in ("category_filter", "category_date") and category:
            return await _category_query(db, user_id, category, start_date, end_date, period)
        elif query_type == "summary":
            return await _summary_query(db, user_id, start_date, end_date, period)
        else:
            return await _date_range_query(db, user_id, start_date, end_date, category, period)

    except QueryError:
        raise
    except Exception as e:
        logger.error(f"Query handling failed: {e}")
        raise QueryError(f"Query failed: {e}")


async def _category_query(
    db: AsyncSession, user_id, category: str, start, end, period: str | None
) -> str:
    """Query expenses for a specific category."""
    expenses = await expense_service.get_expenses(
        db, user_id, start_date=start, end_date=end, category=category
    )

    if not expenses:
        period_label = period or "this period"
        return f"No {category} expenses found for {period_label}."

    total = sum(float(e.amount) for e in expenses)
    header = f"💰 {category} expenses"
    if period:
        header += f" ({period})"
    header += f": {format_currency(total)}"

    lines = [header, ""]
    for e in expenses[:15]:
        date_str = e.date.strftime("%b %d")
        desc = f" — {e.description}" if e.description else ""
        lines.append(f"  • {date_str}: {format_currency(float(e.amount))}{desc}")

    if len(expenses) > 15:
        lines.append(f"  ... and {len(expenses) - 15} more")

    return "\n".join(lines)


async def _summary_query(
    db: AsyncSession, user_id, start, end, period: str | None
) -> str:
    """Generate a summary with category breakdown."""
    categories = await expense_service.get_expenses_by_category(
        db, user_id, start, end
    )

    if not categories:
        return "No expenses found for this period."

    total = sum(categories.values())
    header = format_report_header(period or "today", start, end)

    lines = [header, ""]
    for cat, amount in categories.items():
        pct = (amount / total) * 100 if total > 0 else 0
        lines.append(f"  {cat}: {format_currency(amount)} ({pct:.0f}%)")

    lines.append(f"\n<b>Total: {format_currency(total)}</b>")
    return "\n".join(lines)


async def _date_range_query(
    db: AsyncSession, user_id, start, end, category: str | None, period: str | None
) -> str:
    """Query expenses for a date range with optional category filter."""
    expenses = await expense_service.get_expenses(
        db, user_id, start_date=start, end_date=end, category=category
    )

    if not expenses:
        return "No expenses found for this period."

    total = sum(float(e.amount) for e in expenses)
    header = format_report_header(period or "today", start, end)
    lines = [f"{header}\n<b>Total: {format_currency(total)}</b> ({len(expenses)} expenses)", ""]

    for e in expenses[:20]:
        date_str = e.date.strftime("%b %d, %I:%M %p")
        desc = f" — {e.description}" if e.description else ""
        lines.append(f"  • {format_currency(float(e.amount))} ({e.category}){desc}")

    if len(expenses) > 20:
        lines.append(f"  ... and {len(expenses) - 20} more")

    return "\n".join(lines)
