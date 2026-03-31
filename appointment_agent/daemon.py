"""Background scheduler: appointment reminders + morning/evening check-ins."""

import time
from datetime import datetime

import schedule

from .checkin import run_morning_checkin, run_evening_checkin
from .notify import send
from .store import get_due_reminders, mark_reminded


def _check_reminders():
    for appt in get_due_reminders():
        dt = datetime.fromisoformat(appt["datetime"])
        minutes_until = max(0, int((dt - datetime.now()).total_seconds() / 60))
        msg = f"Starting in {minutes_until} min"
        if appt.get("location"):
            msg += f" · {appt['location']}"
        send(f"📅 Upcoming: {appt['title']}", msg)
        mark_reminded(appt["id"])


def _morning_job():
    try:
        summary = run_morning_checkin()
        print(f"\n[{datetime.now().strftime('%H:%M')}] Morning check-in:\n{summary}\n")
    except Exception as exc:
        print(f"[ERROR] Morning check-in failed: {exc}")


def _evening_job():
    try:
        summary = run_evening_checkin()
        print(f"\n[{datetime.now().strftime('%H:%M')}] Evening check-in:\n{summary}\n")
    except Exception as exc:
        print(f"[ERROR] Evening check-in failed: {exc}")


def start(morning_time: str = "08:00", evening_time: str = "18:00"):
    """Block and run the scheduler loop. Call this in the background process."""
    schedule.every().day.at(morning_time).do(_morning_job)
    schedule.every().day.at(evening_time).do(_evening_job)
    schedule.every(1).minutes.do(_check_reminders)

    print(f"Appointment agent running.")
    print(f"  Morning check-in : {morning_time}")
    print(f"  Evening check-in : {evening_time}")
    print(f"  Reminder polling : every 1 min")
    print("Press Ctrl+C to stop.\n")

    while True:
        schedule.run_pending()
        time.sleep(30)
