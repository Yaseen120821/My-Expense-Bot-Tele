"""
Report generation service — daily, weekly, and monthly reports.
Includes chart generation (matplotlib) and email delivery via Resend API.
"""

import io
import base64
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import expense_service
from app.exceptions.custom_exceptions import ReportError
from app.utils.helpers import (
    format_currency,
    get_date_range,
    format_report_header,
    now_local,
    CURRENCY_SYMBOL,
)
from app.utils.logger import get_logger
from app.config import get_settings

logger = get_logger(__name__)

# Chart styling
CHART_COLORS = [
    "#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd",
    "#818cf8", "#4f46e5", "#7c3aed", "#5b21b6",
    "#e879f9", "#f472b6", "#fb7185", "#f87171",
    "#fbbf24", "#34d399", "#22d3ee", "#60a5fa",
]

CHART_STYLE = {
    "figure.facecolor": "#1a1a2e",
    "axes.facecolor": "#16213e",
    "axes.edgecolor": "#e0e0e0",
    "text.color": "#e0e0e0",
    "xtick.color": "#e0e0e0",
    "ytick.color": "#e0e0e0",
    "axes.labelcolor": "#e0e0e0",
    "font.family": "sans-serif",
}


# ---------------------------------------------------------------------------
# Daily Report (Telegram message)
# ---------------------------------------------------------------------------


async def generate_daily_report(db: AsyncSession, user_id) -> str:
    """
    Generate daily expense summary as a text message.
    Format:
        📊 Today's Summary (Apr 25, 2026)
        Food: ₹500.00
        Transport: ₹150.00
        Total: ₹650.00
    """
    try:
        start, end = get_date_range("today")
        categories = await expense_service.get_expenses_by_category(
            db, user_id, start, end
        )

        if not categories:
            return "📊 Today's Summary\n\nNo expenses recorded today. 🎉"

        total = sum(categories.values())
        header = format_report_header("today", start, end)
        lines = [header, ""]

        for cat, amount in categories.items():
            lines.append(f"{cat}: {format_currency(amount)}")

        lines.append(f"\n<b>Total: {format_currency(total)}</b>")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Daily report generation failed: {e}")
        raise ReportError(f"Daily report failed: {e}")


# ---------------------------------------------------------------------------
# Weekly Report (Email with charts)
# ---------------------------------------------------------------------------


async def generate_weekly_report(
    db: AsyncSession, user_id
) -> tuple[str, list[tuple[str, bytes]]]:
    """
    Generate weekly report with:
    - HTML email body
    - Pie chart (category distribution)
    - Bar chart (daily totals)
    - Week-over-week comparison

    Returns (html_str, [(filename, png_bytes), ...])
    """
    try:
        start, end = get_date_range("week")
        prev_start, prev_end = get_date_range("last_week")

        # Current week data
        categories = await expense_service.get_expenses_by_category(
            db, user_id, start, end
        )
        daily_totals = await expense_service.get_daily_totals(
            db, user_id, start, end
        )
        total = sum(categories.values()) if categories else 0

        # Previous week data
        prev_categories = await expense_service.get_expenses_by_category(
            db, user_id, prev_start, prev_end
        )
        prev_total = sum(prev_categories.values()) if prev_categories else 0

        # Comparison
        comparison = _calculate_comparison(categories, prev_categories)
        total_change = _pct_change(total, prev_total)

        # Generate charts
        attachments = []
        if categories:
            pie = _create_pie_chart(categories, "Category Distribution")
            attachments.append(("pie_chart.png", pie))
        if daily_totals:
            bar = _create_bar_chart(daily_totals, "Daily Spending")
            attachments.append(("bar_chart.png", bar))

        # Build HTML
        header = format_report_header("week", start, end)
        html = _build_report_html(
            title=header,
            total=total,
            total_change=total_change,
            categories=categories,
            comparison=comparison,
            period="week",
            prev_total=prev_total,
            attachments=attachments,
        )

        return html, attachments

    except Exception as e:
        logger.error(f"Weekly report generation failed: {e}")
        raise ReportError(f"Weekly report failed: {e}")


# ---------------------------------------------------------------------------
# Monthly Report (Email with charts)
# ---------------------------------------------------------------------------


async def generate_monthly_report(
    db: AsyncSession, user_id
) -> tuple[str, list[tuple[str, bytes]]]:
    """
    Generate monthly report with charts and month-over-month comparison.
    """
    try:
        start, end = get_date_range("month")
        prev_start, prev_end = get_date_range("last_month")

        categories = await expense_service.get_expenses_by_category(
            db, user_id, start, end
        )
        daily_totals = await expense_service.get_daily_totals(
            db, user_id, start, end
        )
        total = sum(categories.values()) if categories else 0

        prev_categories = await expense_service.get_expenses_by_category(
            db, user_id, prev_start, prev_end
        )
        prev_total = sum(prev_categories.values()) if prev_categories else 0

        comparison = _calculate_comparison(categories, prev_categories)
        total_change = _pct_change(total, prev_total)

        # Charts
        attachments = []
        if categories:
            pie = _create_pie_chart(categories, "Monthly Category Distribution")
            attachments.append(("pie_chart.png", pie))
        if daily_totals:
            bar = _create_bar_chart(daily_totals, "Daily Spending This Month")
            attachments.append(("bar_chart.png", bar))

        # Trend analysis
        days_elapsed = (end - start).days + 1
        avg_daily = total / days_elapsed if days_elapsed > 0 else 0
        trend_lines = []
        for cat, amount in categories.items():
            cat_avg = amount / days_elapsed if days_elapsed > 0 else 0
            trend_lines.append(
                f"Your {cat} spending averaged {format_currency(cat_avg)}/day"
            )

        header = format_report_header("month", start, end)
        html = _build_report_html(
            title=header,
            total=total,
            total_change=total_change,
            categories=categories,
            comparison=comparison,
            period="month",
            prev_total=prev_total,
            attachments=attachments,
            extra_insights=trend_lines[:5],
        )

        return html, attachments

    except Exception as e:
        logger.error(f"Monthly report generation failed: {e}")
        raise ReportError(f"Monthly report failed: {e}")


# ---------------------------------------------------------------------------
# Telegram-formatted summary (for /summary, /weekly, /monthly commands)
# ---------------------------------------------------------------------------


async def generate_summary_text(
    db: AsyncSession, user_id, period: str
) -> str:
    """Generate a text-only summary for Telegram."""
    try:
        start, end = get_date_range(period)
        categories = await expense_service.get_expenses_by_category(
            db, user_id, start, end
        )

        if not categories:
            return f"No expenses found for {period}."

        total = sum(categories.values())
        header = format_report_header(period, start, end)

        # Previous period comparison
        try:
            prev_period = "last_week" if period == "week" else "last_month" if period == "month" else None
            if prev_period:
                prev_start, prev_end = get_date_range(prev_period)
                prev_total = await expense_service.get_total(
                    db, user_id, prev_start, prev_end
                )
                change = _pct_change(total, prev_total)
                change_str = f"\n📈 {change}" if change else ""
            else:
                change_str = ""
        except Exception:
            change_str = ""

        lines = [header, ""]
        for cat, amount in categories.items():
            pct = (amount / total * 100) if total > 0 else 0
            lines.append(f"{cat}: {format_currency(amount)} ({pct:.0f}%)")

        lines.append(f"\n<b>Total: {format_currency(total)}</b>")
        if change_str:
            lines.append(change_str)

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        raise ReportError(f"Summary generation failed: {e}")


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------


def _create_pie_chart(data: dict[str, float], title: str) -> bytes:
    """Create a pie chart and return as PNG bytes."""
    with plt.rc_context(CHART_STYLE):
        fig, ax = plt.subplots(figsize=(8, 6))
        labels = list(data.keys())
        values = list(data.values())
        colors = CHART_COLORS[: len(labels)]

        wedges, texts, autotexts = ax.pie(
            values,
            labels=labels,
            colors=colors,
            autopct=lambda pct: f"{CURRENCY_SYMBOL}{pct * sum(values) / 100:,.0f}\n({pct:.1f}%)",
            startangle=90,
            textprops={"fontsize": 10, "color": "#e0e0e0"},
        )

        for autotext in autotexts:
            autotext.set_fontsize(8)
            autotext.set_color("#ffffff")

        ax.set_title(title, fontsize=14, fontweight="bold", pad=20)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()


def _create_bar_chart(data: dict[str, float], title: str) -> bytes:
    """Create a bar chart of daily spending and return as PNG bytes."""
    with plt.rc_context(CHART_STYLE):
        fig, ax = plt.subplots(figsize=(10, 5))
        dates = list(data.keys())
        values = list(data.values())

        # Shorten date labels
        short_dates = []
        for d in dates:
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                short_dates.append(dt.strftime("%b %d"))
            except ValueError:
                short_dates.append(d)

        bars = ax.bar(short_dates, values, color=CHART_COLORS[0], width=0.6, edgecolor="none")

        # Add value labels on bars
        for bar_item, val in zip(bars, values):
            if val > 0:
                ax.text(
                    bar_item.get_x() + bar_item.get_width() / 2,
                    bar_item.get_height() + max(values) * 0.02,
                    f"{CURRENCY_SYMBOL}{val:,.0f}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color="#e0e0e0",
                )

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_ylabel(f"Amount ({CURRENCY_SYMBOL})")
        ax.yaxis.set_major_formatter(
            ticker.FuncFormatter(lambda x, _: f"{CURRENCY_SYMBOL}{x:,.0f}")
        )
        plt.xticks(rotation=45, ha="right")
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()


# ---------------------------------------------------------------------------
# Comparison & HTML helpers
# ---------------------------------------------------------------------------


def _pct_change(current: float, previous: float) -> str:
    """Calculate and format percentage change."""
    if previous == 0:
        if current > 0:
            return "New spending (no previous data)"
        return ""

    change = ((current - previous) / previous) * 100
    if abs(change) < 0.5:
        return "About the same as last period"
    elif change > 0:
        return f"↑ {change:.1f}% more than last period ({format_currency(previous)})"
    else:
        return f"↓ {abs(change):.1f}% less than last period ({format_currency(previous)})"


def _calculate_comparison(
    current: dict[str, float], previous: dict[str, float]
) -> dict[str, str]:
    """Compare category totals between two periods."""
    result = {}
    all_categories = set(list(current.keys()) + list(previous.keys()))

    for cat in all_categories:
        curr = current.get(cat, 0)
        prev = previous.get(cat, 0)
        result[cat] = _pct_change(curr, prev)

    return result


def _build_report_html(
    title: str,
    total: float,
    total_change: str,
    categories: dict[str, float],
    comparison: dict[str, str],
    period: str,
    prev_total: float,
    attachments: list[tuple[str, bytes]],
    extra_insights: list[str] | None = None,
) -> str:
    """Build HTML email body for weekly/monthly reports."""
    cat_rows = ""
    for cat, amount in categories.items():
        pct = (amount / total * 100) if total > 0 else 0
        change = comparison.get(cat, "")
        cat_rows += f"""
        <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #333;">{cat}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #333;text-align:right;">{format_currency(amount)}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #333;text-align:right;">{pct:.1f}%</td>
            <td style="padding:8px 12px;border-bottom:1px solid #333;font-size:12px;color:#aaa;">{change}</td>
        </tr>"""

    # Chart images as CID references
    chart_html = ""
    for i, (filename, _) in enumerate(attachments):
        cid = filename.replace(".", "_")
        chart_html += f'<img src="cid:{cid}" style="max-width:100%;margin:16px 0;border-radius:8px;" />'

    insights_html = ""
    if extra_insights:
        insights_list = "".join(f"<li>{ins}</li>" for ins in extra_insights)
        insights_html = f"""
        <div style="margin:20px 0;padding:16px;background:#1a1a2e;border-radius:8px;border-left:4px solid #6366f1;">
            <h3 style="margin:0 0 8px;color:#a78bfa;">💡 Insights</h3>
            <ul style="margin:0;padding-left:20px;color:#ccc;">{insights_list}</ul>
        </div>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0;padding:0;background:#0f0f23;color:#e0e0e0;font-family:Arial,Helvetica,sans-serif;">
        <div style="max-width:600px;margin:0 auto;padding:24px;">
            <h1 style="color:#a78bfa;margin-bottom:4px;">{title}</h1>
            <p style="color:#888;margin-top:0;">AI Expense Tracker</p>

            <div style="background:#16213e;border-radius:12px;padding:20px;margin:20px 0;">
                <h2 style="margin:0;color:#e0e0e0;">Total: {format_currency(total)}</h2>
                <p style="margin:4px 0 0;color:#888;font-size:14px;">{total_change}</p>
            </div>

            <table style="width:100%;border-collapse:collapse;background:#16213e;border-radius:8px;overflow:hidden;">
                <thead>
                    <tr style="background:#1a1a2e;">
                        <th style="padding:10px 12px;text-align:left;color:#a78bfa;">Category</th>
                        <th style="padding:10px 12px;text-align:right;color:#a78bfa;">Amount</th>
                        <th style="padding:10px 12px;text-align:right;color:#a78bfa;">Share</th>
                        <th style="padding:10px 12px;text-align:left;color:#a78bfa;">vs Previous</th>
                    </tr>
                </thead>
                <tbody>{cat_rows}</tbody>
            </table>

            {chart_html}
            {insights_html}

            <p style="margin-top:32px;font-size:12px;color:#666;text-align:center;">
                Generated by AI Expense Tracker
            </p>
        </div>
    </body>
    </html>
    """
    return html


# ---------------------------------------------------------------------------
# Email delivery via Resend API
# ---------------------------------------------------------------------------

RESEND_API_URL = "https://api.resend.com/emails"
MAX_EMAIL_RETRIES = 2


async def send_email_report(
    to_email: str,
    subject: str,
    html_body: str,
    attachments: list[tuple[str, bytes]] | None = None,
) -> bool:
    """
    Send an HTML email with optional image attachments via Resend API.

    Args:
        to_email: Recipient email address.
        subject: Email subject line.
        html_body: HTML content of the email.
        attachments: List of (filename, png_bytes) tuples for chart images.

    Returns:
        True if email was sent successfully, False otherwise.
    """
    import httpx

    settings = get_settings()

    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not configured — skipping email report")
        return False

    if not settings.EMAIL_FROM:
        logger.warning("EMAIL_FROM not configured — skipping email report")
        return False

    # Build Resend API payload
    payload: dict = {
        "from": settings.EMAIL_FROM,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }

    # Convert chart images to base64 attachments
    if attachments:
        payload["attachments"] = [
            {
                "filename": filename,
                "content": base64.b64encode(img_bytes).decode("utf-8"),
            }
            for filename, img_bytes in attachments
        ]

    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    # Send with retry
    last_error = None
    for attempt in range(1, MAX_EMAIL_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    RESEND_API_URL,
                    json=payload,
                    headers=headers,
                )

            if response.status_code == 200:
                response_data = response.json()
                email_id = response_data.get("id", "unknown")
                logger.info(
                    f"✅ Email sent via Resend (id={email_id}) to {to_email}"
                )
                return True

            # Non-200 response
            logger.warning(
                f"Resend API returned {response.status_code} "
                f"(attempt {attempt}/{MAX_EMAIL_RETRIES}): {response.text}"
            )
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"

        except httpx.TimeoutException as e:
            logger.warning(
                f"Resend API timeout (attempt {attempt}/{MAX_EMAIL_RETRIES}): {e}"
            )
            last_error = str(e)

        except Exception as e:
            logger.error(
                f"Resend API error (attempt {attempt}/{MAX_EMAIL_RETRIES}): {e}"
            )
            last_error = str(e)

    logger.error(f"Email send failed after {MAX_EMAIL_RETRIES} attempts: {last_error}")
    return False
