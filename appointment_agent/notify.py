"""Desktop notification wrapper with terminal fallback."""

try:
    from plyer import notification as _plyer_notification
    _PLYER_AVAILABLE = True
except ImportError:
    _PLYER_AVAILABLE = False


def send(title: str, message: str, timeout: int = 10) -> bool:
    """Send a desktop notification. Falls back to terminal output if unavailable."""
    if _PLYER_AVAILABLE:
        try:
            _plyer_notification.notify(
                title=title,
                message=message,
                app_name="Appointment Agent",
                timeout=timeout,
            )
            return True
        except Exception:
            pass

    # Terminal fallback
    border = "─" * 50
    print(f"\n┌{border}┐")
    print(f"│ 🔔  {title:<46}│")
    print(f"│{'':>2}{message[:48]:<48}│")
    if len(message) > 48:
        # Wrap remaining message
        rest = message[48:]
        while rest:
            chunk = rest[:48]
            rest = rest[48:]
            print(f"│{'':>2}{chunk:<48}│")
    print(f"└{border}┘\n")
    return False
