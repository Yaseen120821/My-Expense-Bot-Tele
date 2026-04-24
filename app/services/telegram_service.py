"""
Telegram Bot API client.
Handles sending messages, downloading files, and webhook management.
"""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import get_settings
from app.exceptions.custom_exceptions import TelegramAPIError
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Shared async HTTP client (connection pooling)
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


# ---------------------------------------------------------------------------
# Core API helpers
# ---------------------------------------------------------------------------


async def _api_call(method: str, **kwargs) -> dict:
    """Make a Telegram Bot API call."""
    settings = get_settings()
    url = f"{settings.telegram_api_base}/{method}"
    client = _get_client()

    try:
        response = await client.post(url, **kwargs)
        response.raise_for_status()
        result = response.json()

        if not result.get("ok"):
            desc = result.get("description", "Unknown error")
            logger.error(f"Telegram API error: {desc}")
            raise TelegramAPIError(
                message=f"Telegram API: {desc}",
                status_code=result.get("error_code"),
            )
        return result.get("result", {})

    except httpx.HTTPStatusError as e:
        logger.error(f"Telegram HTTP error {e.response.status_code}: {e}")
        raise TelegramAPIError(
            message=str(e), status_code=e.response.status_code
        )
    except httpx.RequestError as e:
        logger.error(f"Telegram request error: {e}")
        raise TelegramAPIError(message=f"Network error: {e}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(TelegramAPIError),
    reraise=True,
)
async def send_message(
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: dict | None = None,
) -> dict:
    """Send a text message to a Telegram chat."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    logger.debug(f"Sending message to chat {chat_id}: {text[:80]}...")
    return await _api_call("sendMessage", json=payload)


async def send_photo(
    chat_id: int,
    photo_bytes: bytes,
    caption: str = "",
) -> dict:
    """Send a photo to a Telegram chat."""
    files = {"photo": ("chart.png", photo_bytes, "image/png")}
    data = {"chat_id": str(chat_id), "caption": caption, "parse_mode": "HTML"}

    logger.debug(f"Sending photo to chat {chat_id}")
    return await _api_call("sendPhoto", data=data, files=files)


async def download_file(file_id: str) -> bytes:
    """Download a file from Telegram servers by file_id."""
    # Step 1: Get file path
    file_info = await _api_call("getFile", json={"file_id": file_id})
    file_path = file_info.get("file_path")
    if not file_path:
        raise TelegramAPIError("Could not get file path from Telegram")

    # Step 2: Download the file
    settings = get_settings()
    url = f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{file_path}"
    client = _get_client()

    try:
        response = await client.get(url)
        response.raise_for_status()
        logger.info(f"Downloaded file {file_id} ({len(response.content)} bytes)")
        return response.content
    except httpx.HTTPError as e:
        logger.error(f"File download failed: {e}")
        raise TelegramAPIError(f"File download failed: {e}")


async def set_webhook(url: str) -> bool:
    """Register a webhook URL with Telegram."""
    logger.info(f"Setting webhook to: {url}")
    result = await _api_call(
        "setWebhook",
        json={
            "url": url,
            "allowed_updates": ["message", "edited_message"],
            "drop_pending_updates": False,
        },
    )
    logger.info(f"Webhook set successfully: {result}")
    return True


async def delete_webhook() -> bool:
    """Remove the current webhook."""
    await _api_call("deleteWebhook", json={"drop_pending_updates": False})
    logger.info("Webhook deleted")
    return True


async def get_webhook_info() -> dict:
    """Get current webhook status."""
    return await _api_call("getWebhookInfo")
