# Google Calendar Bill Agent

An agentic Python system that checks your Google Calendar events and Google Tasks daily, detects due and overdue bills/payments, and sends you an email summary. Runs on a schedule inside Docker using the Gemini API.

---

## How It Works

```
Scheduler wakes up at configured time (e.g. 08:50)
        ↓
Agent calls Google Calendar + Google Tasks via MCP tools
        ↓
Filters results to keyword-matching items (bills, payroll, CIBC, Scotia, etc.)
        ↓
Gemini (gemini-2.5-flash) categorizes into due_today and overdue
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
- Uses the **Gemini API** (Flash by default — fast and free-tier friendly for this workload)
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
- A [Gemini API key](https://aistudio.google.com/apikey) (free tier available)
- A Google Cloud project with **Calendar API** and **Tasks API** enabled
- A Gmail **App Password** for sending email notifications

---

## Setup

### 1. Get a Gemini API key

Create a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and add it to `.env`:

```env
GEMINI_API_KEY=...
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
| `GEMINI_API_KEY` | *(required)* | Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model to use |
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

---

## Deploying for Free with GitHub Actions

Since this agent only needs to run for a few seconds once a day, a scheduled GitHub Actions workflow (`.github/workflows/bill-agent.yml`) is a better fit than a 24/7 hosted container — no server to keep alive, and Actions is free for this workload on both public and private repos.

This bypasses `scheduler.py`/Docker entirely — the workflow's cron trigger replaces the sleep loop, and it runs `src/agent.py` directly.

### 1. Set repository secrets

Go to **Settings → Secrets and variables → Actions** (or use `gh secret set`) and add:

| Secret | Value |
|--------|-------|
| `GEMINI_API_KEY` | Your Gemini API key |
| `GMAIL_APP_PASSWORD` | Your Gmail app password |
| `GOOGLE_CREDENTIALS_JSON` | Contents of `credentials/credentials.json` |
| `GOOGLE_TOKEN_JSON` | Contents of `credentials/token.json` (generate first via `python src/auth.py` locally) |

Using the CLI from the `gcalendar-bill-notification` directory:
```bash
gh secret set GEMINI_API_KEY --body "..."
gh secret set GMAIL_APP_PASSWORD --body "your16charpassword"
gh secret set GOOGLE_CREDENTIALS_JSON < credentials/credentials.json
gh secret set GOOGLE_TOKEN_JSON < credentials/token.json
```

### 2. Adjust the schedule

`config.md`'s `## Schedule` block is ignored in this mode. Edit the `cron:` line in `.github/workflows/bill-agent.yml` instead (cron is always UTC — GitHub doesn't support IANA timezones directly).

### 3. Trigger manually to test

```bash
gh workflow run bill-agent.yml
gh run watch
```

### Notes

- **Refresh tokens**: the workflow doesn't write the refreshed `token.json` back to the secret — this is fine as long as your Google refresh token stays valid. If it's ever revoked (`invalid_grant`), you'll get the existing auth-alert email; re-run `python src/auth.py` locally and update the `GOOGLE_TOKEN_JSON` secret.
- **Public repos**: secrets are encrypted and never printed in logs, so this is safe to use even on a public repo — but don't put personal info (email, keywords) in `config.md` if the repo is public, since that file is tracked in git and visible to anyone.
