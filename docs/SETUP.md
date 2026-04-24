# Setup & Deployment Guide

## Local Development

### 1. Prerequisites

- **Python 3.11+**: [Download](https://www.python.org/downloads/)
- **PostgreSQL 14+**: [Download](https://www.postgresql.org/download/)
- **Git**: [Download](https://git-scm.com/)

### 2. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** (looks like `123456:ABC-DEF...`)
4. Set bot commands:
   ```
   /setcommands
   start - Welcome message
   today - Today's expense summary
   summary - This week's overview
   weekly - Detailed weekly report
   monthly - Monthly report
   delete_last - Undo last expense
   ```

### 3. Get a Gemini API Key

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Click **Create API Key**
3. Copy the key

### 4. Create PostgreSQL Database

```sql
-- Using psql or pgAdmin
CREATE DATABASE expense_tracker;
CREATE USER expense_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE expense_tracker TO expense_user;
```

### 5. Set Up the Project

```bash
# Clone the repository
git clone <repo-url>
cd My_Expense_Tracker

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
copy .env.example .env       # Windows
# cp .env.example .env       # Linux/Mac
```

Edit `.env` with your actual values:
```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
GEMINI_API_KEY=AIzaSy...
DATABASE_URL=postgresql+asyncpg://expense_user:your_password@localhost:5432/expense_tracker?sslmode=require
WEBHOOK_BASE_URL=https://your-ngrok-url.ngrok.io
RESEND_API_KEY=re_your_key_here
EMAIL_FROM=noreply@yourdomain.com
```

### 6. Initialize Database

```bash
python -m app.db.migrations
```

### 7. Start the Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 8. Expose Local Server (for Telegram webhook)

For local development, use [ngrok](https://ngrok.com/) to expose your local server:

```bash
ngrok http 8000
```

Update your `.env` with the ngrok URL:
```env
WEBHOOK_BASE_URL=https://abc123.ngrok.io
```

Restart the server — it will automatically set the webhook on startup.

---

## Production Deployment (Render)

### 1. Create a Render Account

Sign up at [render.com](https://render.com).

### 2. Create PostgreSQL Database

1. Go to Render Dashboard → **New** → **PostgreSQL**
2. Name: `expense-tracker-db`
3. Copy the **Internal Database URL**

### 3. Create Web Service

1. Go to **New** → **Web Service**
2. Connect your GitHub repository
3. Configure:
   - **Name:** `expense-tracker`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### 4. Set Environment Variables

In the Render service settings → **Environment**:

| Key | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | Your bot token |
| `GEMINI_API_KEY` | Your Gemini key |
| `DATABASE_URL` | Neon PostgreSQL URL (`postgresql+asyncpg://...?sslmode=require`) |
| `WEBHOOK_BASE_URL` | `https://expense-tracker.onrender.com` |
| `APP_ENV` | `production` |
| `LOG_LEVEL` | `INFO` |
| `RESEND_API_KEY` | Your Resend API key |
| `EMAIL_FROM` | Your verified sender email |

> **⚠️ Important:** If using Render PostgreSQL, URLs start with `postgres://`. Change this to `postgresql+asyncpg://` and append `?sslmode=require` for Neon compatibility.

### 5. Deploy

Push to your connected GitHub branch and Render will auto-deploy.

### 6. Verify

1. Check the deploy logs for `✅ Application startup complete`
2. Visit `https://expense-tracker.onrender.com/health`
3. Send `/start` to your bot on Telegram

---

## Docker Deployment (Optional)

### Dockerfile

```dockerfile
FROM python:3.11-slim

# Install Tesseract OCR (optional)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: expense_tracker
      POSTGRES_USER: expense_user
      POSTGRES_PASSWORD: your_password
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

volumes:
  pgdata:
```

```bash
docker-compose up --build
```

---

## Deployment Checklist

- [ ] Set all environment variables
- [ ] `DATABASE_URL` uses `postgresql+asyncpg://` prefix
- [ ] PostgreSQL database created
- [ ] Schema initialized (`python -m app.db.migrations`)
- [ ] Webhook URL is publicly accessible (HTTPS)
- [ ] Bot token is valid (test with `https://api.telegram.org/bot<TOKEN>/getMe`)
- [ ] Gemini API key is valid
- [ ] Health endpoint returns `{"status": "healthy"}`
- [ ] Send `/start` to bot and receive welcome message
- [ ] APScheduler running (check logs for "Scheduler started")
- [ ] Resend API key valid (email reports configured)
- [ ] Logging enabled and accessible
- [ ] Test full flow: add expense → query → delete

---

## Troubleshooting

### Bot not responding
1. Check webhook: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
2. Verify URL is correct and returns 200
3. Check server logs for errors

### Database connection errors
1. Verify `DATABASE_URL` format: `postgresql+asyncpg://user:pass@host:5432/dbname`
2. Check PostgreSQL is running and accessible
3. Verify credentials

### Gemini API errors
1. Check API key is valid
2. Verify model name (`gemini-2.0-flash`)
3. Check API quotas at [Google AI Studio](https://makersuite.google.com/)

### Scheduler not running
1. Check logs for "Scheduler configured" message
2. Verify timezone setting (`REPORT_TIMEZONE`)
3. Ensure the app is not running in multiple instances (APScheduler is in-process)

### Email reports not sending
1. Verify `RESEND_API_KEY` is set and valid
2. Ensure `EMAIL_FROM` uses a verified domain on Resend
3. Check logs for Resend API response codes
4. Test at [Resend Dashboard](https://resend.com/emails)
