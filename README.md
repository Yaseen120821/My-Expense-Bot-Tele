# AI Expense Tracker 💰

An AI-powered expense tracking system that integrates **Telegram Bot API** with **Google Gemini AI** for autonomous expense tracking, receipt processing, and automated financial reporting.

## ✨ Features

- **Natural Language Parsing**: Send messages like "₹200 on lunch" or "50 coffee and 100 uber yesterday"
- **Receipt OCR**: Upload receipt photos — AI extracts amount, items, and category
- **Smart Categorization**: Auto-categorizes expenses using context and AI inference
- **Interactive Queries**: Ask "How much did I spend on food this week?" in natural language
- **Automated Reports**: Daily summaries (Telegram), weekly/monthly reports (email with charts)
- **Anomaly Detection**: Flags unusual spending patterns
- **Multi-User**: Isolated expense tracking per Telegram user

## 🏗️ Architecture

```
┌─────────────┐     Webhook      ┌──────────────┐
│  Telegram   │ ───────────────► │   FastAPI     │
│  Bot API    │ ◄─────────────── │   Backend     │
└─────────────┘   Send Message   └──────┬───────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
              ┌─────▼─────┐     ┌──────▼──────┐     ┌─────▼─────┐
              │  Gemini   │     │ PostgreSQL  │     │ APScheduler│
              │  AI API   │     │  Database   │     │  Reports   │
              └───────────┘     └─────────────┘     └───────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Google Gemini API Key

### Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd My_Expense_Tracker

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
copy .env.example .env
# Edit .env with your actual values

# 5. Initialize database
python -m app.db.migrations

# 6. Run the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | Bot token from @BotFather |
| `GEMINI_API_KEY` | ✅ | Google Gemini API key |
| `DATABASE_URL` | ✅ | Neon PostgreSQL connection string |
| `WEBHOOK_BASE_URL` | ✅ | Public URL (e.g., `https://app.onrender.com`) |
| `RESEND_API_KEY` | ❌ | Resend API key for email reports |
| `EMAIL_FROM` | ❌ | Verified sender email (Resend) |
| `REPORT_TIMEZONE` | ❌ | Timezone (default: Asia/Kolkata) |
| `DAILY_REPORT_HOUR` | ❌ | Hour for daily report (default: 21) |

## 📱 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message & instructions |
| `/today` | Today's expense summary |
| `/summary` | This week's overview |
| `/weekly` | Detailed weekly breakdown |
| `/monthly` | Monthly report |
| `/delete_last` | Undo the last expense |

## 💬 Usage Examples

**Adding expenses:**
```
₹200 on lunch
50 coffee and 100 uber
Spent 1200 on groceries from BigBasket yesterday
```

**Querying:**
```
How much did I spend on food this week?
Show expenses for Monday
What did I spend yesterday?
```

**Receipt processing:**
- Send a photo of a receipt → Bot reads it → Confirm or reject

## 🧪 Testing

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=term-missing

# Run integration tests (requires real API keys)
pytest tests/ -v --run-integration
```

## 📊 API Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

See [docs/API.md](docs/API.md) for detailed endpoint documentation.

## 🚢 Deployment

See [docs/SETUP.md](docs/SETUP.md) for deployment instructions (Render, Docker, etc.).

## 📁 Project Structure

```
expense-tracker/
├── app/
│   ├── main.py                 # FastAPI app + lifespan
│   ├── config.py               # Pydantic settings
│   ├── routes/
│   │   └── telegram_webhook.py # Webhook handler
│   ├── services/
│   │   ├── ai_service.py       # Gemini AI (text + vision)
│   │   ├── expense_service.py  # CRUD & business logic
│   │   ├── report_service.py   # Report generation + charts
│   │   ├── ocr_service.py      # Receipt OCR
│   │   ├── query_service.py    # NL queries
│   │   └── telegram_service.py # Telegram API client
│   ├── models/
│   │   ├── expense.py          # Expense + PendingConfirmation
│   │   └── user.py             # User model
│   ├── db/
│   │   ├── database.py         # Async engine + sessions
│   │   └── migrations.py       # Schema creation
│   ├── scheduler/
│   │   └── jobs.py             # Cron jobs
│   ├── utils/
│   │   ├── validators.py       # Input validation
│   │   ├── helpers.py          # Formatting + dates
│   │   └── logger.py           # Logging config
│   └── exceptions/
│       └── custom_exceptions.py
├── tests/
│   ├── unit/                   # Unit tests (mocked)
│   ├── integration/            # Integration tests
│   └── conftest.py             # Fixtures
├── docs/
│   ├── API.md
│   └── SETUP.md
├── requirements.txt
├── .env.example
└── .gitignore
```

## 📄 License

MIT
