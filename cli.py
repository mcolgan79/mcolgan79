#!/usr/bin/env python3
"""Appointment Agent CLI — manage appointments, tasks, and check-ins."""

from datetime import datetime

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def cli():
    """AI-powered appointment & task agent.

    Runs daily morning/evening check-ins via Claude and sends desktop
    reminders before appointments.
    """


# ── Appointments ─────────────────────────────────────────────────────────────

@cli.command("add-appointment")
@click.argument("title")
@click.argument("when", metavar="DATETIME")
@click.option("--duration", "-d", default=60, show_default=True, help="Duration in minutes.")
@click.option("--location", "-l", default="", help="Location or meeting link.")
@click.option("--notes", "-n", default="", help="Extra notes.")
@click.option("--reminder", "-r", default=15, show_default=True, help="Remind N minutes before.")
def add_appointment(title, when, duration, location, notes, reminder):
    """Add an appointment.

    DATETIME format: 'YYYY-MM-DD HH:MM'  e.g. '2024-06-15 14:00'
    """
    from appointment_agent.store import add_appointment as _add
    try:
        dt = datetime.strptime(when, "%Y-%m-%d %H:%M")
    except ValueError:
        console.print("[red]Bad date format.[/red] Use: YYYY-MM-DD HH:MM")
        raise SystemExit(1)

    _add(title, dt, duration, location, notes, reminder)
    console.print(
        f"[green]✓[/green] Added: [bold]{title}[/bold] — "
        f"{dt.strftime('%a %b %d at %I:%M %p')}"
    )


@cli.command("delete-appointment")
@click.argument("appointment_id")
def delete_appointment(appointment_id):
    """Delete an appointment by its ID (from 'list')."""
    from appointment_agent.store import delete_appointment as _del
    if _del(appointment_id):
        console.print(f"[green]✓[/green] Appointment {appointment_id!r} deleted.")
    else:
        console.print(f"[red]Not found:[/red] {appointment_id!r}")


# ── Tasks ─────────────────────────────────────────────────────────────────────

@cli.command("add-task")
@click.argument("title")
@click.option("--description", "-d", default="", help="Task description.")
@click.option("--due", default=None, metavar="DATE", help="Due date YYYY-MM-DD.")
@click.option(
    "--priority", "-p",
    type=click.Choice(["low", "medium", "high"]),
    default="medium",
    show_default=True,
)
@click.option("--notes", "-n", default="", help="Extra notes.")
def add_task(title, description, due, priority, notes):
    """Add a task."""
    from appointment_agent.store import add_task as _add
    due_dt = None
    if due:
        try:
            due_dt = datetime.strptime(due, "%Y-%m-%d")
        except ValueError:
            console.print("[red]Bad date format.[/red] Use: YYYY-MM-DD")
            raise SystemExit(1)
    _add(title, description, due_dt, priority, notes)
    console.print(f"[green]✓[/green] Task added: [bold]{title}[/bold]")


@cli.command("complete")
@click.argument("task_ref", metavar="ID_OR_TITLE")
def complete_task(task_ref):
    """Mark a task complete (ID prefix or exact title)."""
    from appointment_agent.store import complete_task as _complete
    task = _complete(task_ref)
    if task:
        console.print(f"[green]✓[/green] Completed: [bold]{task['title']}[/bold]")
    else:
        console.print(f"[red]Task not found:[/red] {task_ref!r}")


@cli.command("delete-task")
@click.argument("task_ref", metavar="ID_OR_TITLE")
def delete_task(task_ref):
    """Delete a task (ID prefix or exact title)."""
    from appointment_agent.store import delete_task as _del
    if _del(task_ref):
        console.print(f"[green]✓[/green] Task deleted.")
    else:
        console.print(f"[red]Not found:[/red] {task_ref!r}")


# ── List ──────────────────────────────────────────────────────────────────────

@cli.command("list")
@click.option("--days", default=7, show_default=True, help="Upcoming days to show.")
@click.option("--all-tasks", "show_all", is_flag=True, help="Show completed tasks too.")
def list_all(days, show_all):
    """List upcoming appointments and tasks."""
    from appointment_agent.store import list_appointments, get_pending_tasks, get_all_tasks

    # Appointments
    appts = list_appointments(upcoming_days=days)
    appt_table = Table(title=f"📅 Appointments (next {days} days)", show_header=True, header_style="bold cyan")
    appt_table.add_column("Date & Time")
    appt_table.add_column("Title", style="bold")
    appt_table.add_column("Location")
    appt_table.add_column("Reminder")
    appt_table.add_column("ID", style="dim")

    if appts:
        for a in appts:
            dt = datetime.fromisoformat(a["datetime"])
            appt_table.add_row(
                dt.strftime("%a %b %d  %I:%M %p"),
                a["title"],
                a.get("location", ""),
                f"{a.get('reminder_minutes', 15)} min",
                a["id"][:8],
            )
    else:
        appt_table.add_row(f"No appointments in the next {days} days", "", "", "", "")

    console.print(appt_table)

    # Tasks
    tasks = get_all_tasks() if show_all else get_pending_tasks()
    task_table = Table(
        title="✅ Tasks" + (" (all)" if show_all else " (pending)"),
        show_header=True,
        header_style="bold green",
    )
    task_table.add_column("Title", style="bold")
    task_table.add_column("Priority")
    task_table.add_column("Due")
    task_table.add_column("Status")
    task_table.add_column("ID", style="dim")

    priority_colors = {"high": "red", "medium": "yellow", "low": "green"}
    status_colors = {"pending": "yellow", "completed": "green"}

    if tasks:
        for t in tasks:
            pri = t.get("priority", "medium")
            status = t.get("status", "pending")
            task_table.add_row(
                t["title"],
                f"[{priority_colors.get(pri, 'white')}]{pri}[/]",
                (t.get("due_date") or "—")[:10],
                f"[{status_colors.get(status, 'white')}]{status}[/]",
                t["id"][:8],
            )
    else:
        task_table.add_row("No tasks", "", "", "", "")

    console.print(task_table)


# ── Check-ins ─────────────────────────────────────────────────────────────────

@cli.command("checkin")
@click.argument("kind", type=click.Choice(["morning", "evening"]))
def checkin(kind):
    """Run a manual morning or evening check-in."""
    from appointment_agent.checkin import run_morning_checkin, run_evening_checkin
    console.print(f"Running [bold]{kind}[/bold] check-in…")
    try:
        summary = run_morning_checkin() if kind == "morning" else run_evening_checkin()
        console.print("\n[bold green]Check-in summary:[/bold green]")
        console.print(summary)
    except RuntimeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1)


# ── Daemon ────────────────────────────────────────────────────────────────────

@cli.command("start")
@click.option("--morning", default="08:00", show_default=True, help="Morning check-in time HH:MM.")
@click.option("--evening", default="18:00", show_default=True, help="Evening check-in time HH:MM.")
def start(morning, evening):
    """Start the background agent (blocks; run with & or via a service)."""
    from appointment_agent.daemon import start as _start
    _start(morning_time=morning, evening_time=evening)


if __name__ == "__main__":
    cli()
