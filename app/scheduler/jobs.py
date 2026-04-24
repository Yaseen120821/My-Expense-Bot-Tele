"""
APScheduler jobs for automated report delivery.
- Daily report: sent via Telegram at configurable hour
- Weekly report: sent via email on Sunday morning
- Monthly report: sent via email on the 1st of each month
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.db.database import get_session_factory
from app.services import expense_service, report_service, telegram_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


def setup_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    global _scheduler
    settings = get_settings()

    _scheduler = AsyncIOScheduler(timezone=settings.REPORT_TIMEZONE)

    # --- Daily report (Telegram) ---
    _scheduler.add_job(
        _daily_report_job,
        CronTrigger(
            hour=settings.DAILY_REPORT_HOUR,
            minute=0,
            timezone=settings.REPORT_TIMEZONE,
        ),
        id="daily_report",
        name="Daily Expense Report",
        replace_existing=True,
    )

    # --- Weekly report (Email) ---
    _scheduler.add_job(
        _weekly_report_job,
        CronTrigger(
            day_of_week=settings.WEEKLY_REPORT_DAY,
            hour=settings.WEEKLY_REPORT_HOUR,
            minute=0,
            timezone=settings.REPORT_TIMEZONE,
        ),
        id="weekly_report",
        name="Weekly Expense Report",
        replace_existing=True,
    )

    # --- Monthly report (Email, 1st of month) ---
    _scheduler.add_job(
        _monthly_report_job,
        CronTrigger(
            day=1,
            hour=settings.MONTHLY_REPORT_HOUR,
            minute=0,
            timezone=settings.REPORT_TIMEZONE,
        ),
        id="monthly_report",
        name="Monthly Expense Report",
        replace_existing=True,
    )

    # --- Cleanup expired pending confirmations ---
    _scheduler.add_job(
        _cleanup_pending_confirmations,
        CronTrigger(hour="*/6", timezone=settings.REPORT_TIMEZONE),
        id="cleanup_pending",
        name="Cleanup Expired Confirmations",
        replace_existing=True,
    )

    logger.info(
        f"Scheduler configured: daily@{settings.DAILY_REPORT_HOUR}:00, "
        f"weekly@{settings.WEEKLY_REPORT_DAY} {settings.WEEKLY_REPORT_HOUR}:00, "
        f"monthly@1st {settings.MONTHLY_REPORT_HOUR}:00"
    )
    return _scheduler


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler


# ---------------------------------------------------------------------------
# Job implementations
# ---------------------------------------------------------------------------


async def _daily_report_job() -> None:
    """Send daily summary to all users via Telegram."""
    logger.info("Running daily report job...")
    factory = get_session_factory()

    try:
        async with factory() as db:
            users = await expense_service.get_all_users(db)
            logger.info(f"Generating daily reports for {len(users)} users")

            for user in users:
                try:
                    report_text = await report_service.generate_daily_report(
                        db, user.id
                    )
                    await telegram_service.send_message(
                        user.telegram_id, report_text
                    )
                    logger.info(f"Daily report sent to user {user.telegram_id}")
                except Exception as e:
                    logger.error(
                        f"Daily report failed for user {user.telegram_id}: {e}"
                    )

            await db.commit()

    except Exception as e:
        logger.error(f"Daily report job failed: {e}")


async def _weekly_report_job() -> None:
    """Generate and email weekly reports to all users with email."""
    logger.info("Running weekly report job...")
    factory = get_session_factory()

    try:
        async with factory() as db:
            users = await expense_service.get_all_users(db)

            for user in users:
                try:
                    # Always send Telegram summary
                    summary = await report_service.generate_summary_text(
                        db, user.id, "week"
                    )
                    await telegram_service.send_message(
                        user.telegram_id, summary
                    )

                    # Send email if configured
                    if user.email:
                        html, attachments = await report_service.generate_weekly_report(
                            db, user.id
                        )
                        await report_service.send_email_report(
                            user.email,
                            "📊 Your Weekly Expense Report",
                            html,
                            attachments,
                        )
                        logger.info(f"Weekly email sent to {user.email}")

                except Exception as e:
                    logger.error(
                        f"Weekly report failed for user {user.telegram_id}: {e}"
                    )

            await db.commit()

    except Exception as e:
        logger.error(f"Weekly report job failed: {e}")


async def _monthly_report_job() -> None:
    """Generate and email monthly reports."""
    logger.info("Running monthly report job...")
    factory = get_session_factory()

    try:
        async with factory() as db:
            users = await expense_service.get_all_users(db)

            for user in users:
                try:
                    # Telegram summary
                    summary = await report_service.generate_summary_text(
                        db, user.id, "month"
                    )
                    await telegram_service.send_message(
                        user.telegram_id, summary
                    )

                    # Email report
                    if user.email:
                        html, attachments = await report_service.generate_monthly_report(
                            db, user.id
                        )
                        await report_service.send_email_report(
                            user.email,
                            "📊 Your Monthly Expense Report",
                            html,
                            attachments,
                        )
                        logger.info(f"Monthly email sent to {user.email}")

                except Exception as e:
                    logger.error(
                        f"Monthly report failed for user {user.telegram_id}: {e}"
                    )

            await db.commit()

    except Exception as e:
        logger.error(f"Monthly report job failed: {e}")


async def _cleanup_pending_confirmations() -> None:
    """Remove pending confirmations older than 1 hour."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import delete
    from app.models.expense import PendingConfirmation

    factory = get_session_factory()
    try:
        async with factory() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            stmt = delete(PendingConfirmation).where(
                PendingConfirmation.created_at < cutoff
            )
            result = await db.execute(stmt)
            await db.commit()
            if result.rowcount > 0:
                logger.info(f"Cleaned up {result.rowcount} expired pending confirmations")
    except Exception as e:
        logger.error(f"Cleanup job failed: {e}")
