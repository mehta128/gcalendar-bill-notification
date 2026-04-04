"""Bill-checking agent: uses Ollama + Google Calendar MCP to detect due/overdue bills."""

import asyncio
import json
import os
import re
import smtplib
import sys
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI

load_dotenv()

LOG_FILE = Path(os.getenv("LOG_FILE", "/logs/bills.log"))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}")
logger.add(str(LOG_FILE), level="INFO", rotation="1 week", retention="4 weeks",
           format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5")

CONFIG_FILE = Path(__file__).parent.parent / "config.md"


def load_config() -> tuple[list[str], dict[str, str]]:
    """Parse config.md and return (keywords, email_config)."""
    keywords: list[str] = []
    email: dict[str, str] = {}

    if not CONFIG_FILE.exists():
        return keywords, email

    text = CONFIG_FILE.read_text()

    # Extract fenced blocks in order: first = keywords, second = email
    blocks = re.findall(r"```\n(.*?)```", text, re.DOTALL)

    if len(blocks) >= 1:
        keywords = [line.strip() for line in blocks[0].strip().splitlines() if line.strip()]

    if len(blocks) >= 2:
        for line in blocks[1].strip().splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                email[key.strip()] = val.strip()

    return keywords, email


def matches_keywords(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def filter_items(items: list[dict], keywords: list[str]) -> list[dict]:
    """Keep only items whose title or notes/description match a keyword."""
    result = []
    for item in items:
        combined = " ".join([
            item.get("title", ""),
            item.get("description", ""),
            item.get("notes", ""),
        ])
        if matches_keywords(combined, keywords):
            result.append(item)
    return result


SYSTEM_PROMPT = """You are a personal finance assistant. Your job is to:
1. Call BOTH tools: get_todays_events and get_pending_tasks.
2. From today's calendar events AND all pending tasks, identify anything that matches the user's keyword list.
3. For tasks, flag any with is_overdue=true as overdue.
4. Return ONLY a valid JSON object, no extra text:
{
  "checked_at": "<ISO datetime>",
  "due_today": [{"title": "...", "due_date": "...", "description": "..."}],
  "overdue": [{"title": "...", "due_date": "...", "description": "..."}],
  "summary": "<brief human-readable summary>"
}

Rules:
- due_today: matching calendar events today OR matching tasks with due_date = today
- overdue: matching tasks where is_overdue=true
- If nothing found in a category, use []
- Always call BOTH tools before responding."""


async def run_agent():
    logger.info("Starting bill-check agent run")
    today = datetime.now().strftime("%Y-%m-%d")

    keywords, email_config = load_config()
    logger.info(f"Loaded {len(keywords)} keywords from config.md")

    mcp_script = Path(__file__).parent / "calendar_mcp.py"
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(mcp_script)],
        env={
            **os.environ,
            "GOOGLE_CREDENTIALS_FILE": os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials/credentials.json"),
            "GOOGLE_TOKEN_FILE": os.getenv("GOOGLE_TOKEN_FILE", "credentials/token.json"),
        },
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = await session.list_tools()
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    },
                }
                for tool in mcp_tools.tools
            ]
            logger.info(f"MCP tools available: {[t['function']['name'] for t in tools]}")

            client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
            keyword_list = ", ".join(keywords) if keywords else "bill, payment, payroll, credit card, rent"
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Today is {today}. "
                        f"Keywords to match: {keyword_list}. "
                        "Call both tools, filter results to only items matching these keywords, "
                        "then return the JSON."
                    ),
                },
            ]

            for _ in range(5):
                response = client.chat.completions.create(
                    model=OLLAMA_MODEL,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )

                msg = response.choices[0].message
                finish_reason = response.choices[0].finish_reason
                messages.append(msg)

                if finish_reason == "tool_calls" and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        name = tool_call.function.name
                        args = json.loads(tool_call.function.arguments or "{}")
                        logger.info(f"Calling MCP tool: {name}")
                        result = await session.call_tool(name, args)
                        raw_content = result.content[0].text if result.content else "[]"

                        # Filter raw tool results to keyword-matching items only
                        try:
                            raw_items = json.loads(raw_content)
                            if isinstance(raw_items, dict) and raw_items.get("error") == "auth_required":
                                logger.error(f"Auth required: {raw_items.get('message')}")
                                _send_auth_alert_email(email_config, raw_items.get("message", ""))
                                return
                            if isinstance(raw_items, list):
                                filtered = filter_items(raw_items, keywords)
                                content = json.dumps(filtered, indent=2)
                                print(f"\n--- {name} ({len(filtered)}/{len(raw_items)} items matched) ---\n{content}\n---\n")
                            else:
                                content = raw_content
                                print(f"\n--- {name} ---\n{content}\n---\n")
                        except (json.JSONDecodeError, ValueError):
                            content = raw_content
                            print(f"\n--- {name} ---\n{content}\n---\n")

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": content,
                        })
                else:
                    _log_results(msg.content or "", today, email_config)
                    break
            else:
                logger.warning("Reached max iterations without final answer")


def _log_results(result_text: str, today: str, email_config: dict):
    logger.info("=" * 60)
    logger.info(f"Bill check complete for {today}")

    try:
        text = result_text.strip()
        if "```" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            text = text[start:end]

        data = json.loads(text)

        due_today = data.get("due_today", [])
        overdue = data.get("overdue", [])

        if due_today:
            logger.warning(f"BILLS DUE TODAY ({len(due_today)}):")
            for bill in due_today:
                logger.warning(f"  [DUE TODAY] {bill.get('title')} | {bill.get('due_date')} | {bill.get('description', '')}")
        else:
            logger.info("No bills due today.")

        if overdue:
            logger.error(f"OVERDUE BILLS ({len(overdue)}):")
            for bill in overdue:
                logger.error(f"  [OVERDUE]   {bill.get('title')} | {bill.get('due_date')} | {bill.get('description', '')}")
        else:
            logger.info("No overdue bills found.")

        logger.info(f"Summary: {data.get('summary', '')}")

        # Send email
        _send_email(due_today, overdue, today, email_config)

    except (json.JSONDecodeError, ValueError):
        logger.info(f"Agent response:\n{result_text}")

    logger.info("=" * 60)


def _send_email(due_today: list, overdue: list, today: str, email_config: dict):
    if not due_today and not overdue:
        logger.info("Nothing to email.")
        return

    app_password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not app_password:
        logger.warning("GMAIL_APP_PASSWORD not set — skipping email.")
        return

    to_addr = email_config.get("to", "")
    from_addr = email_config.get("from", "")
    subject_template = email_config.get("subject", "Bill & Payroll Reminder — {date}")
    smtp_host = email_config.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(email_config.get("smtp_port", "587"))
    subject = subject_template.replace("{date}", today)

    body_lines = [
        "Hi,",
        "",
        "Here is your bill and payroll reminder for today:",
        "",
    ]

    if due_today:
        body_lines.append("DUE TODAY:")
        for bill in due_today:
            desc = f" — {bill.get('description')}" if bill.get("description") else ""
            body_lines.append(f"  • {bill.get('title')} (due {bill.get('due_date')}){desc}")
        body_lines.append("")

    if overdue:
        body_lines.append("OVERDUE (action required):")
        for bill in overdue:
            desc = f" — {bill.get('description')}" if bill.get("description") else ""
            body_lines.append(f"  • {bill.get('title')} (was due {bill.get('due_date')}){desc}")
        body_lines.append("")

    body_lines += ["Please action the above at your earliest convenience.", "", "Regards,", "Bill Agent"]

    msg = MIMEText("\n".join(body_lines))
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(from_addr, app_password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        logger.info(f"Email sent to {to_addr}: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")


def _send_auth_alert_email(email_config: dict, message: str):
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not app_password:
        logger.warning("GMAIL_APP_PASSWORD not set — cannot send auth alert email.")
        return
    to_addr = email_config.get("to", "")
    from_addr = email_config.get("from", "")
    smtp_host = email_config.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(email_config.get("smtp_port", "587"))
    body = (
        "Your Google Calendar bill agent needs re-authentication.\n\n"
        f"Error: {message}\n\n"
        "To fix:\n"
        "  1. On your local machine (not Docker): python src/auth.py\n"
        "  2. Restart Docker: docker compose restart\n\n"
        "Regards,\nBill Agent"
    )
    msg = MIMEText(body)
    msg["Subject"] = "ACTION REQUIRED: Bill Agent — Google re-authentication needed"
    msg["From"] = from_addr
    msg["To"] = to_addr
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(from_addr, app_password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        logger.info(f"Auth alert email sent to {to_addr}")
    except Exception as e:
        logger.error(f"Failed to send auth alert email: {e}")


if __name__ == "__main__":
    asyncio.run(run_agent())
