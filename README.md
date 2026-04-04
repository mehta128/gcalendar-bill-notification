# Google Calendar Bill Agent

An agentic Python system that checks your Google Calendar events and Google Tasks daily, detects due and overdue bills/payments, and sends you an email summary. Runs on a schedule inside Docker using a local Ollama LLM — no paid AI API required.

---

## How It Works

```
Scheduler wakes up at configured time (e.g. 08:50)
        ↓
Agent calls Google Calendar + Google Tasks via MCP tools
        ↓
Filters results to keyword-matching items (bills, payroll, CIBC, Scotia, etc.)
        ↓
LLM (Ollama / qwen2.5) categorizes into due_today and overdue
        ↓
Sends email summary → logs to bills.log
        ↓
Sleeps until same time tomorrow
```

---

## Features

- Checks **Google Calendar events** and **Google Tasks** in one run
- Keyword filtering — only bill/payment-related items are processed
- Detects **due today** and **overdue** items separately
- Sends a **daily email** with a structured summary
- Runs entirely **free** — local Ollama LLM, no paid APIs
- Fully **Dockerized** with persistent credentials and logs
- Schedule and keywords configurable via a single `config.md` file — no code changes needed

---

## Project Structure

```
gcalendar-bill-notification/
├── src/
│   ├── agent.py          # Main agent — agentic loop, LLM, email sending
│   ├── scheduler.py      # Long-running scheduler — reads config, triggers agent daily
│   ├── calendar_mcp.py   # MCP server — exposes Google Calendar + Tasks as tools
│   └── auth.py           # One-time OAuth authentication script
├── credentials/
│   ├── credentials.json  # Google OAuth client credentials (you provide)
│   └── token.json        # Auto-generated after first auth run
├── logs/
│   └── bills.log         # Persistent log of all agent runs
├── config.md             # Edit this to change keywords, email, and schedule
├── .env                  # Secrets and environment variables
├── Dockerfile
└── docker-compose.yml
```

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Ollama](https://ollama.com) installed and running on your host machine
- A Google Cloud project with **Calendar API** and **Tasks API** enabled
- A Gmail **App Password** for sending email notifications

---

## Setup

### 1. Pull the Ollama model

```bash
ollama pull qwen2.5
```

### 2. Google Cloud credentials

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → enable **Google Calendar API** and **Google Tasks API**
3. Create **OAuth 2.0 credentials** (Desktop app type)
4. Download `credentials.json` → place it in the `credentials/` folder
5. Add your Gmail address as a test user in the OAuth consent screen

### 3. Authenticate with Google (one-time)

```bash
cd gcalendar-bill-notification
pip install poetry
poetry install
poetry run python src/auth.py
```

A browser window will open — log in and allow access. This creates `credentials/token.json` which auto-refreshes forever.

### 4. Gmail App Password

1. Enable 2-Step Verification on your Google account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create an app password named "Bill Agent"
4. Copy the 16-character password into `.env`:

```env
GMAIL_APP_PASSWORD=yourpasswordhere
```

### 5. Configure keywords, email, and schedule

Edit `config.md`:

```markdown
## Keywords
bill, payment, CIBC, Scotia, payroll, ...

## Email
to: you@gmail.com
from: you@gmail.com

## Schedule
time: 08:50
timezone: America/Toronto
```

### 6. Start with Docker

```bash
docker compose build
docker compose up -d
```

Check logs:
```bash
docker compose logs -f
```

---

## Configuration Reference (`config.md`)

| Section | What to edit |
|---------|-------------|
| `## Keywords` | Add/remove words to match in task/event titles. One per line. |
| `## Email` | Set `to`, `from`, `subject`, SMTP settings |
| `## Schedule` | Set `time` (24h HH:MM) and `timezone` |

After editing `config.md`, restart the container to pick up changes:
```bash
docker compose restart
```
No rebuild required — `config.md` is mounted as a live volume.

---

## Environment Variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama API endpoint |
| `OLLAMA_MODEL` | `qwen2.5` | Model to use |
| `GOOGLE_CREDENTIALS_FILE` | `credentials/credentials.json` | OAuth credentials path |
| `GOOGLE_TOKEN_FILE` | `credentials/token.json` | OAuth token path |
| `LOG_FILE` | `logs/bills.log` | Log file path |
| `GMAIL_APP_PASSWORD` | *(required)* | Gmail App Password for sending email |

---

## Running Locally (without Docker)

```bash
poetry install
poetry run python src/agent.py
```

---

## Example Email Output

```
Subject: Bill & Payroll Reminder — 2026-03-28

Hi,

Here is your bill and payroll reminder for today:

OVERDUE (action required):
  • run payroll for 30th (was due 2026-03-26)
  • Cibc master card payment (was due 2026-03-25)
  • Scotia Scene Credit Card Payment (was due 2026-03-24)

Please action the above at your earliest convenience.

Regards,
Bill Agent
```

---

## Scheduling

The container runs 24/7 and sleeps until the configured time. It uses your local timezone so the trigger is always at the right wall-clock time regardless of the server's UTC offset.

To change the run time, edit `config.md` and restart:
```bash
docker compose restart
```

To auto-start on system boot: **Docker Desktop → Settings → General → Start Docker Desktop when you log in**.
