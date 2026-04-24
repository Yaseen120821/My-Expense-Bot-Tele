"""
Custom exception classes for the expense tracker.
"""


class ExpenseTrackerError(Exception):
    """Base exception for the application."""

    def __init__(self, message: str = "An unexpected error occurred", user_message: str | None = None):
        super().__init__(message)
        # User-friendly message safe to show in Telegram
        self.user_message = user_message or message


class AIParsingError(ExpenseTrackerError):
    """Raised when Gemini API fails to parse expense data."""

    def __init__(self, message: str = "Failed to parse expense", raw_response: str | None = None):
        super().__init__(
            message=message,
            user_message="I couldn't understand that. Try something like: '₹200 on lunch' or '50 coffee'",
        )
        self.raw_response = raw_response


class TelegramAPIError(ExpenseTrackerError):
    """Raised when Telegram Bot API call fails."""

    def __init__(self, message: str = "Telegram API error", status_code: int | None = None):
        super().__init__(
            message=message,
            user_message="Something went wrong sending the message. Please try again.",
        )
        self.status_code = status_code


class DatabaseError(ExpenseTrackerError):
    """Raised for database operation failures."""

    def __init__(self, message: str = "Database error"):
        super().__init__(
            message=message,
            user_message="There was a problem saving your data. Please try again.",
        )


class ValidationError(ExpenseTrackerError):
    """Raised for input validation failures."""

    def __init__(self, message: str = "Validation error", details: str | None = None):
        user_msg = details or "Invalid input. Please check and try again."
        super().__init__(message=message, user_message=user_msg)
        self.details = details


class OCRError(ExpenseTrackerError):
    """Raised when OCR/receipt processing fails."""

    def __init__(self, message: str = "OCR processing failed"):
        super().__init__(
            message=message,
            user_message="I couldn't read that receipt. Please try a clearer photo, or type the expense manually.",
        )


class QueryError(ExpenseTrackerError):
    """Raised when an interactive query fails."""

    def __init__(self, message: str = "Query processing failed"):
        super().__init__(
            message=message,
            user_message="I couldn't process that query. Try: 'How much did I spend on food this week?'",
        )


class ReportError(ExpenseTrackerError):
    """Raised when report generation fails."""

    def __init__(self, message: str = "Report generation failed"):
        super().__init__(
            message=message,
            user_message="There was a problem generating your report. Please try again later.",
        )
