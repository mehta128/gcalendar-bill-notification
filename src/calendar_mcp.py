"""MCP server exposing Google Calendar and Google Tasks tools."""

import json
import os
from datetime import datetime
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks.readonly",
]
CREDENTIALS_FILE = Path(os.getenv("GOOGLE_CREDENTIALS_FILE", "/credentials/credentials.json"))
TOKEN_FILE = Path(os.getenv("GOOGLE_TOKEN_FILE", "/credentials/token.json"))

app = Server("google-calendar-tasks")


def get_credentials():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return creds


def get_calendar_service():
    return build("calendar", "v3", credentials=get_credentials())


def get_tasks_service():
    return build("tasks", "v1", credentials=get_credentials())


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_todays_events",
            description="Fetch all Google Calendar events scheduled for today across all calendars.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="get_pending_tasks",
            description="Fetch all incomplete tasks from Google Tasks across all task lists, including due dates.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    now = datetime.now().astimezone()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    if name == "get_todays_events":
        service = get_calendar_service()
        calendars = service.calendarList().list().execute().get("items", [])
        events = []
        for cal in calendars:
            result = (
                service.events()
                .list(
                    calendarId=cal["id"],
                    timeMin=today_start.isoformat(),
                    timeMax=today_end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            for e in result.get("items", []):
                e["_calendar"] = cal.get("summary", cal["id"])
                events.append(e)
        # Return only relevant fields to keep payload small
        slim = [
            {
                "title": e.get("summary", ""),
                "description": e.get("description", ""),
                "start": e.get("start", {}),
                "end": e.get("end", {}),
                "calendar": e.get("_calendar", ""),
            }
            for e in events
        ]
        return [types.TextContent(type="text", text=json.dumps(slim, indent=2))]

    elif name == "get_pending_tasks":
        try:
            service = get_tasks_service()
            tasklists = service.tasklists().list().execute().get("items", [])
        except Exception as e:
            return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]

        today_str = now.strftime("%Y-%m-%d")
        all_tasks = []
        for tl in tasklists:
            result = (
                service.tasks()
                .list(tasklist=tl["id"], showCompleted=False, showHidden=False)
                .execute()
            )
            for task in result.get("items", []):
                due = task.get("due", "")
                due_date = due[:10] if due else ""
                all_tasks.append({
                    "title": task.get("title", ""),
                    "notes": task.get("notes", ""),
                    "due_date": due_date,
                    "is_overdue": bool(due_date and due_date < today_str),
                    "tasklist": tl.get("title", ""),
                })
        return [types.TextContent(type="text", text=json.dumps(all_tasks, indent=2))]

    return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
