"""
Telegram Webhook endpoint — receives all Telegram updates and routes them
to the appropriate handler (commands, text messages, photo uploads).
"""

from fastapi import APIRouter, Request, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db, get_session_factory
from app.services import (
    telegram_service,
    ai_service,
    expense_service,
    ocr_service,
    query_service,
    report_service,
)
from app.models.expense import ExpenseSource
from app.utils.validators import validate_expense, validate_telegram_update
from app.utils.helpers import (
    format_expense_confirmation,
    format_receipt_confirmation,
    format_currency,
    get_date_range,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

START_MESSAGE = """👋 <b>Welcome to AI Expense Tracker!</b>

I help you track your expenses just by chatting with me.

<b>How to add expenses:</b>
• Send text: "₹200 on lunch" or "50 coffee and 100 uber"
• Send a receipt photo — I'll read it for you!

<b>Commands:</b>
/today — Today's summary
/summary — This week's overview
/weekly — Detailed weekly report
/monthly — Monthly report
/delete_last — Undo last expense

<b>Ask me anything:</b>
"How much did I spend on food this week?"
"Show expenses for yesterday"

Let's get started! 💰"""


@router.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive Telegram webhook updates.
    Returns 200 OK immediately and processes in the background.
    """
    try:
        data = await request.json()
    except Exception:
        return {"ok": True}

    if not validate_telegram_update(data):
        return {"ok": True}

    # Process in background so Telegram gets a fast 200 OK
    background_tasks.add_task(_process_update, data)
    return {"ok": True}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "expense-tracker"}


# ---------------------------------------------------------------------------
# Update processing (runs in background)
# ---------------------------------------------------------------------------


async def _process_update(data: dict) -> None:
    """Route update to appropriate handler."""
    try:
        message = data.get("message") or data.get("edited_message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        telegram_id = message["from"]["id"]
        first_name = message["from"].get("first_name", "")

        # Get a DB session from the factory (not FastAPI dependency)
        factory = get_session_factory()
        async with factory() as db:
            try:
                # Ensure user exists
                user = await expense_service.get_or_create_user(
                    db, telegram_id, first_name
                )

                if "photo" in message:
                    await _handle_photo(db, user, chat_id, message)
                elif "text" in message:
                    text = message["text"].strip()
                    if text.startswith("/"):
                        await _handle_command(db, user, chat_id, text)
                    else:
                        await _handle_text(db, user, chat_id, text)

                db.commit()

            except Exception as e:
                db.rollback()
                logger.error(f"Error processing update: {e}", exc_info=True)
                await _send_error(chat_id, str(e))

    except Exception as e:
        logger.error(f"Fatal error in update processing: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def _handle_command(db: Session, user, chat_id: int, text: str) -> None:
    """Route /commands to their handlers."""
    command = text.split()[0].lower()
    # Strip @botname suffix if present
    if "@" in command:
        command = command.split("@")[0]

    logger.info(f"Command: {command} from user {user.telegram_id}")

    match command:
        case "/start":
            await telegram_service.send_message(chat_id, START_MESSAGE)

        case "/today":
            report = await report_service.generate_daily_report(db, user.id)
            await telegram_service.send_message(chat_id, report)

        case "/summary":
            summary = await report_service.generate_summary_text(db, user.id, "week")
            await telegram_service.send_message(chat_id, summary)

        case "/weekly":
            summary = await report_service.generate_summary_text(db, user.id, "week")
            await telegram_service.send_message(chat_id, summary)

        case "/monthly":
            summary = await report_service.generate_summary_text(db, user.id, "month")
            await telegram_service.send_message(chat_id, summary)

        case "/delete_last":
            deleted = await expense_service.delete_last_expense(db, user.id)
            if deleted:
                msg = (
                    f"🗑️ Deleted: {format_currency(float(deleted.amount))} "
                    f"({deleted.category})"
                )
            else:
                msg = "No expenses to delete."
            await telegram_service.send_message(chat_id, msg)

        case _:
            await telegram_service.send_message(
                chat_id,
                "Unknown command. Try /start to see available commands.",
            )


# ---------------------------------------------------------------------------
# Text message handler
# ---------------------------------------------------------------------------


async def _handle_text(db: Session, user, chat_id: int, text: str) -> None:
    """
    Handle free-text messages:
    1. Check for pending confirmation (Yes/No)
    2. Check if it's a query
    3. Otherwise, parse as expense
    """
    text_lower = text.lower().strip()

    # --- Check for pending confirmation ---
    pending = await expense_service.get_pending_confirmation(db, user.id)
    if pending:
        if text_lower in ("yes", "y", "confirm", "ok", "save"):
            await _confirm_pending(db, user, chat_id, pending)
            return
        elif text_lower in ("no", "n", "cancel", "reject", "discard"):
            await expense_service.clear_pending_confirmation(db, user.id)
            await telegram_service.send_message(chat_id, "❌ Discarded. Send another receipt or expense.")
            return

    # --- Check if it looks like a query ---
    query_indicators = [
        "how much", "show", "what", "report", "total", "summary",
        "list", "spent", "spending", "expenses for", "last",
    ]
    is_query = any(indicator in text_lower for indicator in query_indicators)

    if is_query:
        try:
            response = await query_service.handle_query(db, user.id, text)
            await telegram_service.send_message(chat_id, response)
            return
        except Exception as e:
            logger.warning(f"Query handling failed, trying expense parse: {e}")

    # --- Parse as expense ---
    try:
        parsed = await ai_service.parse_expense_text(text)

        if not parsed:
            await telegram_service.send_message(
                chat_id,
                "I couldn't parse any expense from that. Try: '₹50 on coffee' or 'spent 200 on lunch'",
            )
            return

        # Validate and save each expense
        saved_expenses = []
        for item in parsed:
            try:
                validated = validate_expense(item)
                expense = await expense_service.add_expense(
                    db=db,
                    user_id=user.id,
                    amount=validated["amount"],
                    category=validated["category"],
                    date=validated.get("date"),
                    description=validated.get("description"),
                    source=ExpenseSource.TEXT,
                )
                saved_expenses.append({
                    "amount": validated["amount"],
                    "category": validated["category"],
                })

                # Check for anomalies
                anomaly = await expense_service.detect_anomalies(
                    db, user.id, validated["amount"]
                )
                if anomaly:
                    await telegram_service.send_message(chat_id, anomaly)

            except ValueError as e:
                await telegram_service.send_message(
                    chat_id, f"⚠️ Skipped one entry: {e}"
                )

        if saved_expenses:
            msg = format_expense_confirmation(saved_expenses)
            await telegram_service.send_message(chat_id, msg)

    except Exception as e:
        logger.error(f"Expense parsing failed: {e}")
        await telegram_service.send_message(
            chat_id,
            "I couldn't understand that. Try: '₹50 on coffee' or '200 lunch yesterday'",
        )


# ---------------------------------------------------------------------------
# Photo handler
# ---------------------------------------------------------------------------


async def _handle_photo(db: Session, user, chat_id: int, message: dict) -> None:
    """Handle receipt image upload."""
    try:
        # Get the largest photo (last in the array)
        photos = message["photo"]
        file_id = photos[-1]["file_id"]

        await telegram_service.send_message(chat_id, "🔍 Processing your receipt...")

        # Download image
        image_bytes = await telegram_service.download_file(file_id)

        # OCR processing
        result = await ocr_service.process_receipt(image_bytes)

        # Store as pending confirmation
        await expense_service.store_pending_confirmation(
            db, user.id, chat_id, result
        )

        # Ask user to confirm
        msg = format_receipt_confirmation(result)
        await telegram_service.send_message(chat_id, msg)

    except Exception as e:
        logger.error(f"Photo processing failed: {e}")
        await telegram_service.send_message(
            chat_id,
            "I couldn't read that receipt. Please try a clearer photo, or type the expense manually.",
        )


# ---------------------------------------------------------------------------
# Confirm pending receipt
# ---------------------------------------------------------------------------


async def _confirm_pending(
    db: Session, user, chat_id: int, pending
) -> None:
    """Confirm and save a pending receipt expense."""
    try:
        data = pending.data
        expense = await expense_service.add_expense(
            db=db,
            user_id=user.id,
            amount=float(data.get("amount", 0)),
            category=data.get("category", "Other"),
            description="Receipt: " + ", ".join(data.get("items", [])[:3]),
            source=ExpenseSource.IMAGE,
        )
        await expense_service.clear_pending_confirmation(db, user.id)

        msg = f"✅ Saved {format_currency(float(data['amount']))} ({data.get('category', 'Other')})"
        await telegram_service.send_message(chat_id, msg)

    except Exception as e:
        logger.error(f"Confirmation save failed: {e}")
        await telegram_service.send_message(
            chat_id, "Failed to save. Please try again."
        )


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------


async def _send_error(chat_id: int, error_msg: str) -> None:
    """Send a generic error message to the user."""
    try:
        await telegram_service.send_message(
            chat_id,
            "Something went wrong. Please try again in a moment.",
        )
    except Exception:
        logger.error("Failed to send error message to user")
