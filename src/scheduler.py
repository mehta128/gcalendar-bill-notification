"""Long-running scheduler: reads run time from config.md and triggers agent daily."""

import asyncio
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime
import zoneinfo

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

LOG_FILE = Path(os.getenv("LOG_FILE", "/logs/bills.log"))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}")
logger.add(str(LOG_FILE), level="INFO", rotation="1 week", retention="4 weeks",
           format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

CONFIG_FILE = Path(__file__).parent.parent / "config.md"


def load_schedule() -> tuple[str, str]:
    """Parse config.md Schedule block. Returns (HH:MM, timezone)."""
    run_time = "23:30"
    timezone = "America/Toronto"

    if not CONFIG_FILE.exists():
        return run_time, timezone

    text = CONFIG_FILE.read_text()
    # Find the Schedule fenced block (third ``` block)
    blocks = re.findall(r"```\n(.*?)```", text, re.DOTALL)
    # Schedule block is the third one (keywords=0, email=1, schedule=2)
    schedule_block = blocks[2] if len(blocks) >= 3 else ""

    for line in schedule_block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if key == "time":
                run_time = val
            elif key == "timezone":
                timezone = val

    return run_time, timezone


def seconds_until(run_time: str, tz: zoneinfo.ZoneInfo) -> float:
    """Return seconds until the next occurrence of HH:MM in the given timezone."""
    now = datetime.now(tz)
    hour, minute = map(int, run_time.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        # Already passed today — schedule for tomorrow
        from datetime import timedelta
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def main():
    from agent import run_agent  # imported here to avoid circular issues

    while True:
        run_time, timezone_str = load_schedule()
        try:
            tz = zoneinfo.ZoneInfo(timezone_str)
        except Exception:
            logger.warning(f"Unknown timezone '{timezone_str}', falling back to UTC")
            tz = zoneinfo.ZoneInfo("UTC")

        wait = seconds_until(run_time, tz)
        from datetime import timedelta
        next_run_dt = datetime.now(tz) + timedelta(seconds=wait)
        next_run = next_run_dt.strftime(f"%Y-%m-%d %H:%M {timezone_str}")
        logger.info(f"Next run scheduled at {next_run} (in {wait/3600:.1f}h)")

        time.sleep(wait)

        logger.info("Scheduled trigger — starting agent")
        try:
            await run_agent()
        except Exception as e:
            logger.error(f"Agent run failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
