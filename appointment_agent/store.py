"""JSON-based data store for appointments and tasks."""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path.home() / ".appointment_agent"
DATA_FILE = DATA_DIR / "data.json"


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        _write({"appointments": [], "tasks": [], "checkin_log": []})


def _read():
    _ensure_data_dir()
    with open(DATA_FILE) as f:
        return json.load(f)


def _write(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


# --- Appointments ---

def add_appointment(title, dt, duration_minutes=60, location="", notes="", reminder_minutes=15):
    data = _read()
    appointment = {
        "id": str(uuid.uuid4()),
        "title": title,
        "datetime": dt.isoformat() if isinstance(dt, datetime) else dt,
        "duration_minutes": duration_minutes,
        "location": location,
        "notes": notes,
        "reminder_minutes": reminder_minutes,
        "reminded": False,
    }
    data["appointments"].append(appointment)
    _write(data)
    return appointment


def delete_appointment(appointment_id):
    data = _read()
    before = len(data["appointments"])
    data["appointments"] = [a for a in data["appointments"] if a["id"] != appointment_id]
    _write(data)
    return len(data["appointments"]) < before


def get_todays_appointments():
    data = _read()
    today = datetime.now().date()
    return sorted(
        [a for a in data["appointments"] if datetime.fromisoformat(a["datetime"]).date() == today],
        key=lambda a: a["datetime"],
    )


def list_appointments(upcoming_days=7):
    data = _read()
    now = datetime.now()
    cutoff = now + timedelta(days=upcoming_days)
    return sorted(
        [a for a in data["appointments"] if now <= datetime.fromisoformat(a["datetime"]) <= cutoff],
        key=lambda a: a["datetime"],
    )


def get_due_reminders():
    """Return appointments whose reminder window has arrived but haven't been reminded yet."""
    data = _read()
    now = datetime.now()
    due = []
    for a in data["appointments"]:
        dt = datetime.fromisoformat(a["datetime"])
        minutes_until = (dt - now).total_seconds() / 60
        if not a.get("reminded") and 0 <= minutes_until <= a.get("reminder_minutes", 15):
            due.append(a)
    return due


def mark_reminded(appointment_id):
    data = _read()
    for a in data["appointments"]:
        if a["id"] == appointment_id:
            a["reminded"] = True
    _write(data)


# --- Tasks ---

def add_task(title, description="", due_date=None, priority="medium", notes=""):
    data = _read()
    task = {
        "id": str(uuid.uuid4()),
        "title": title,
        "description": description,
        "due_date": due_date.strftime("%Y-%m-%d") if isinstance(due_date, datetime) else due_date,
        "priority": priority,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
        "notes": notes,
    }
    data["tasks"].append(task)
    _write(data)
    return task


def complete_task(task_ref):
    """Complete a task by ID prefix or title (case-insensitive)."""
    data = _read()
    for task in data["tasks"]:
        if (
            task["id"].startswith(task_ref)
            or task["title"].lower() == task_ref.lower()
        ):
            task["status"] = "completed"
            task["completed_at"] = datetime.now().isoformat()
            _write(data)
            return task
    return None


def delete_task(task_ref):
    data = _read()
    before = len(data["tasks"])
    data["tasks"] = [
        t for t in data["tasks"]
        if not (t["id"].startswith(task_ref) or t["title"].lower() == task_ref.lower())
    ]
    _write(data)
    return len(data["tasks"]) < before


def get_pending_tasks():
    data = _read()
    return [t for t in data["tasks"] if t["status"] == "pending"]


def get_all_tasks():
    return _read()["tasks"]


def get_completed_today():
    data = _read()
    today = datetime.now().date()
    return [
        t for t in data["tasks"]
        if t.get("completed_at")
        and datetime.fromisoformat(t["completed_at"]).date() == today
    ]


# --- Check-in log ---

def log_checkin(checkin_type, summary):
    data = _read()
    data["checkin_log"].append({
        "type": checkin_type,
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
    })
    # Keep last 90 entries
    data["checkin_log"] = data["checkin_log"][-90:]
    _write(data)
