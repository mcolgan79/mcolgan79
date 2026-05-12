#!/usr/bin/env python3
"""
Daily calendar reminder script.

Reads today's events from Google Calendar and sends a push notification
via ntfy.sh. Designed to run as a scheduled GitHub Actions job.

Required environment variables:
  GOOGLE_SERVICE_ACCOUNT_JSON  — contents of a Google service account key JSON file
  NTFY_TOPIC                   — ntfy.sh topic name (e.g. "mcolgan79-reminders")

Optional environment variables:
  GOOGLE_CALENDAR_ID           — calendar ID to read (defaults to "primary")
  NTFY_TOKEN                   — Bearer token for private ntfy topics
  NTFY_SERVER                  — ntfy server URL (defaults to "https://ntfy.sh")
  TIMEZONE                     — IANA timezone (defaults to "America/New_York")
"""

import datetime
import json
import os
import sys

import pytz
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def get_service():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        sys.exit("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON is not set")

    info = json.loads(raw)
    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    )
    return build("calendar", "v3", credentials=credentials)


def fetch_events(service, tz: datetime.tzinfo) -> list:
    today = datetime.datetime.now(tz).date()
    time_min = datetime.datetime.combine(today, datetime.time.min).replace(tzinfo=tz)
    time_max = datetime.datetime.combine(today, datetime.time.max).replace(tzinfo=tz)
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

    try:
        result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except HttpError as e:
        sys.exit(f"ERROR: Google Calendar API error: {e}")

    return result.get("items", [])


def format_event(event: dict, tz: datetime.tzinfo) -> str:
    summary = event.get("summary", "(No title)")
    start = event["start"]

    if "dateTime" in start:
        dt = datetime.datetime.fromisoformat(start["dateTime"]).astimezone(tz)
        end_dt = datetime.datetime.fromisoformat(event["end"]["dateTime"]).astimezone(tz)
        time_str = f"{dt.strftime('%I:%M %p')} – {end_dt.strftime('%I:%M %p')}"
    else:
        time_str = "All day"

    location = event.get("location", "").strip()
    parts = [f"• {time_str}  {summary}"]
    if location:
        parts.append(f"  📍 {location}")
    return "\n".join(parts)


def build_message(events: list, tz: datetime.tzinfo) -> tuple[str, str]:
    today = datetime.datetime.now(tz)
    date_str = today.strftime("%A, %B %-d")
    title = f"📅 {date_str}"

    if not events:
        body = "No events today — enjoy the open day!"
    else:
        count = len(events)
        header = f"{count} event{'s' if count != 1 else ''} today:\n"
        body = header + "\n\n".join(format_event(e, tz) for e in events)

    return title, body


def send_notification(title: str, body: str) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        sys.exit("ERROR: NTFY_TOPIC is not set")

    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    url = f"{server}/{topic}"

    headers = {
        "Title": title,
        "Priority": "default",
        "Tags": "calendar,spiral_calendar",
    }

    token = os.environ.get("NTFY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=15)
    resp.raise_for_status()


def main() -> None:
    tz_name = os.environ.get("TIMEZONE", "America/New_York")
    tz = pytz.timezone(tz_name)

    service = get_service()
    events = fetch_events(service, tz)
    title, body = build_message(events, tz)

    send_notification(title, body)

    print(f"Sent: {title}")
    print(body)


if __name__ == "__main__":
    main()
