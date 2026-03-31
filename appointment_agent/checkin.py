"""Claude-powered morning and evening check-ins."""

import os
from datetime import datetime

import anthropic

from .store import (
    get_todays_appointments,
    get_pending_tasks,
    get_completed_today,
    log_checkin,
)
from .notify import send


def _fmt_appointments(appointments: list) -> str:
    if not appointments:
        return "  (none)"
    lines = []
    for a in appointments:
        dt = datetime.fromisoformat(a["datetime"])
        line = f"  • {dt.strftime('%I:%M %p')} — {a['title']}"
        if a.get("location"):
            line += f"  [{a['location']}]"
        if a.get("notes"):
            line += f"  (note: {a['notes']})"
        lines.append(line)
    return "\n".join(lines)


def _fmt_tasks(tasks: list) -> str:
    if not tasks:
        return "  (none)"
    priority_order = {"high": 0, "medium": 1, "low": 2}
    sorted_tasks = sorted(tasks, key=lambda t: priority_order.get(t.get("priority", "medium"), 1))
    lines = []
    for t in sorted_tasks:
        due = f"  [due {t['due_date']}]" if t.get("due_date") else ""
        pri = f"  [{t['priority']}]" if t.get("priority", "medium") != "medium" else ""
        lines.append(f"  • {t['title']}{due}{pri}")
    return "\n".join(lines)


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Export it before running the agent."
        )
    return anthropic.Anthropic(api_key=api_key)


def run_morning_checkin() -> str:
    """Generate and deliver a morning briefing via Claude."""
    now = datetime.now()
    appointments = get_todays_appointments()
    tasks = get_pending_tasks()

    context = f"""Today is {now.strftime('%A, %B %d, %Y')} — {now.strftime('%I:%M %p')}.

Today's appointments:
{_fmt_appointments(appointments)}

Pending tasks:
{_fmt_tasks(tasks)}"""

    prompt = (
        f"{context}\n\n"
        "Please give a warm, concise morning briefing (3–5 sentences). "
        "Highlight any time-sensitive appointments, suggest a priority order for tasks, "
        "and end with an encouraging note for the day."
    )

    client = _get_client()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )

    summary = response.content[0].text
    log_checkin("morning", summary)
    send("🌅 Good Morning!", summary[:250] + ("…" if len(summary) > 250 else ""))
    return summary


def run_evening_checkin() -> str:
    """Generate and deliver an evening wrap-up via Claude."""
    now = datetime.now()
    appointments = get_todays_appointments()
    completed = get_completed_today()
    pending = get_pending_tasks()

    completed_str = "\n".join(f"  • {t['title']}" for t in completed) or "  (none)"

    context = f"""Today is {now.strftime('%A, %B %d, %Y')} — {now.strftime('%I:%M %p')}.

Today's appointments:
{_fmt_appointments(appointments)}

Tasks completed today:
{completed_str}

Still pending:
{_fmt_tasks(pending)}"""

    prompt = (
        f"{context}\n\n"
        "Please give a warm, concise evening wrap-up (3–5 sentences). "
        "Acknowledge what was accomplished, note any overdue or high-priority pending items, "
        "and suggest what to focus on first tomorrow. End with a restful close."
    )

    client = _get_client()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )

    summary = response.content[0].text
    log_checkin("evening", summary)
    send("🌙 Evening Wrap-Up", summary[:250] + ("…" if len(summary) > 250 else ""))
    return summary
