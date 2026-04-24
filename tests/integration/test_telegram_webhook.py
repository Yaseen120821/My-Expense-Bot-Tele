"""
Integration tests for Telegram webhook endpoint.
Tests the full request → route → response flow using FastAPI TestClient.
"""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app


# ---------------------------------------------------------------------------
# Test client fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    """Create an async test client without running startup/shutdown lifecycle."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Webhook endpoint tests
# ---------------------------------------------------------------------------


class TestWebhookEndpoint:
    """Test POST /webhook endpoint."""

    @pytest.mark.asyncio
    async def test_webhook_returns_200_for_valid_update(
        self, client: AsyncClient, mock_telegram_text_update
    ):
        """Webhook must return 200 OK immediately regardless of processing."""
        with patch("app.routes.telegram_webhook._process_update", new_callable=AsyncMock):
            response = await client.post("/webhook", json=mock_telegram_text_update)
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_webhook_returns_200_for_invalid_json(self, client: AsyncClient):
        response = await client.post(
            "/webhook",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_webhook_returns_200_for_empty_body(self, client: AsyncClient):
        response = await client.post(
            "/webhook",
            json={},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_webhook_command_update(
        self, client: AsyncClient, mock_telegram_command_update
    ):
        with patch("app.routes.telegram_webhook._process_update", new_callable=AsyncMock):
            response = await client.post("/webhook", json=mock_telegram_command_update)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_webhook_photo_update(
        self, client: AsyncClient, mock_telegram_photo_update
    ):
        with patch("app.routes.telegram_webhook._process_update", new_callable=AsyncMock):
            response = await client.post("/webhook", json=mock_telegram_photo_update)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Test GET /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


# ---------------------------------------------------------------------------
# Root endpoint tests
# ---------------------------------------------------------------------------


class TestRootEndpoint:
    """Test GET / endpoint."""

    @pytest.mark.asyncio
    async def test_root(self, client: AsyncClient):
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "AI Expense Tracker"
        assert "version" in data


# ---------------------------------------------------------------------------
# Update processing tests (mocked services)
# ---------------------------------------------------------------------------


class TestUpdateProcessing:
    """Test the _process_update background function."""

    @pytest.mark.asyncio
    @patch("app.routes.telegram_webhook.telegram_service")
    @patch("app.routes.telegram_webhook.ai_service")
    @patch("app.routes.telegram_webhook.expense_service")
    @patch("app.routes.telegram_webhook.get_session_factory")
    async def test_process_text_expense(
        self, mock_factory, mock_es, mock_ai, mock_tg, mock_telegram_text_update
    ):
        from app.routes.telegram_webhook import _process_update

        # Setup mocks
        mock_user = MagicMock()
        mock_user.id = "test-uuid"
        mock_user.telegram_id = 123456789

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_factory_instance = MagicMock()
        mock_factory_instance.return_value = mock_session
        mock_factory.return_value = mock_factory_instance

        mock_es.get_or_create_user = AsyncMock(return_value=mock_user)
        mock_es.get_pending_confirmation = AsyncMock(return_value=None)
        mock_es.add_expense = AsyncMock()
        mock_es.detect_anomalies = AsyncMock(return_value=None)

        mock_ai.parse_expense_text = AsyncMock(return_value=[
            {"amount": 200.0, "category": "Food", "description": "lunch", "date": "2026-04-25"}
        ])

        mock_tg.send_message = AsyncMock()

        await _process_update(mock_telegram_text_update)

        mock_ai.parse_expense_text.assert_called_once()
        mock_tg.send_message.assert_called()

    @pytest.mark.asyncio
    @patch("app.routes.telegram_webhook.telegram_service")
    @patch("app.routes.telegram_webhook.expense_service")
    @patch("app.routes.telegram_webhook.get_session_factory")
    async def test_process_start_command(
        self, mock_factory, mock_es, mock_tg, mock_telegram_command_update
    ):
        from app.routes.telegram_webhook import _process_update

        mock_user = MagicMock()
        mock_user.id = "test-uuid"
        mock_user.telegram_id = 123456789

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_factory_instance = MagicMock()
        mock_factory_instance.return_value = mock_session
        mock_factory.return_value = mock_factory_instance

        mock_es.get_or_create_user = AsyncMock(return_value=mock_user)

        # Change command to /start
        mock_telegram_command_update["message"]["text"] = "/start"

        mock_tg.send_message = AsyncMock()

        await _process_update(mock_telegram_command_update)
        mock_tg.send_message.assert_called()
        call_args = mock_tg.send_message.call_args[0]
        assert "Welcome" in call_args[1]
