# API Documentation

## Base URL

```
https://your-app.onrender.com
```

---

## Endpoints

### `GET /`

Root endpoint — returns API information.

**Response:**
```json
{
    "service": "AI Expense Tracker",
    "version": "1.0.0",
    "docs": "/docs",
    "health": "/health"
}
```

---

### `GET /health`

Health check endpoint.

**Response:**
```json
{
    "status": "healthy",
    "service": "expense-tracker"
}
```

---

### `POST /webhook`

Telegram webhook endpoint. Receives updates from Telegram Bot API.

**Headers:**
```
Content-Type: application/json
```

**Request Body (Text Message):**
```json
{
    "update_id": 100001,
    "message": {
        "message_id": 1,
        "from": {
            "id": 123456789,
            "first_name": "John",
            "is_bot": false
        },
        "chat": {
            "id": 123456789,
            "type": "private"
        },
        "date": 1714000000,
        "text": "spent 200 on lunch"
    }
}
```

**Request Body (Photo/Receipt):**
```json
{
    "update_id": 100002,
    "message": {
        "message_id": 2,
        "from": {
            "id": 123456789,
            "first_name": "John",
            "is_bot": false
        },
        "chat": {
            "id": 123456789,
            "type": "private"
        },
        "date": 1714000000,
        "photo": [
            {
                "file_id": "AgACAgI...",
                "width": 800,
                "height": 600,
                "file_size": 45000
            }
        ]
    }
}
```

**Request Body (Command):**
```json
{
    "update_id": 100003,
    "message": {
        "message_id": 3,
        "from": {
            "id": 123456789,
            "first_name": "John",
            "is_bot": false
        },
        "chat": {
            "id": 123456789,
            "type": "private"
        },
        "date": 1714000000,
        "text": "/today"
    }
}
```

**Response (always):**
```json
{
    "ok": true
}
```

**Status Code:** `200 OK` (always — Telegram requires fast response)

**Processing:** Updates are processed asynchronously in the background. The webhook immediately returns 200 OK.

---

## Supported Commands

| Command | Description | Bot Response |
|---------|-------------|-------------|
| `/start` | Initialize bot | Welcome message with instructions |
| `/today` | Today's summary | Category breakdown + total |
| `/summary` | Weekly overview | Category breakdown + percentages |
| `/weekly` | Weekly report | Detailed weekly summary |
| `/monthly` | Monthly report | Monthly breakdown |
| `/delete_last` | Undo last | Confirmation of deleted expense |

---

## Message Types

### Text Expense
User sends: `"₹200 on lunch"`
Bot responds: `"✅ Added ₹200.00 (Food)"`

### Multiple Expenses
User sends: `"50 coffee and 100 uber"`
Bot responds:
```
✅ Added 2 expenses:
  ₹50.00 (Coffee)
  ₹100.00 (Transport)
```

### Receipt Image
1. User sends photo
2. Bot responds: `"🔍 Processing your receipt..."`
3. Bot responds: `"🧾 Detected ₹540.00 (Food).\nItems: Biryani, Naan\n\nConfirm? Reply Yes or No"`
4. User sends: `"Yes"`
5. Bot responds: `"✅ Saved ₹540.00 (Food)"`

### Natural Language Query
User sends: `"How much did I spend on food this week?"`
Bot responds:
```
💰 Food expenses (week): ₹1,200.00

  • Apr 25: ₹200.00 — lunch
  • Apr 24: ₹500.00 — dinner
  • Apr 23: ₹500.00 — groceries
```

---

## Error Responses

| Scenario | Bot Response |
|----------|-------------|
| Unparseable text | "I couldn't understand that. Try: '₹50 on coffee' or '200 lunch yesterday'" |
| OCR failure | "I couldn't read that receipt. Please try a clearer photo, or type the expense manually." |
| Query failure | "I couldn't process that query. Try: 'How much did I spend on food this week?'" |
| No expenses to delete | "No expenses to delete." |
| Server error | "Something went wrong. Please try again in a moment." |

---

## Interactive API Documentation

- **Swagger UI:** `GET /docs`
- **ReDoc:** `GET /redoc`
