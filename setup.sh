#!/usr/bin/env bash
# Setup script for the Appointment Agent

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="appointment-agent"

echo "=== Appointment Agent Setup ==="
echo ""

# 1. Install Python dependencies
echo "Installing dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
echo "  ✓ Dependencies installed"

# 2. Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo ""
    echo "  ⚠  ANTHROPIC_API_KEY is not set."
    echo "  Add this to your ~/.bashrc or ~/.zshrc:"
    echo "    export ANTHROPIC_API_KEY='sk-ant-...'"
    echo ""
fi

# 3. Optionally install as a systemd user service (Linux only)
if command -v systemctl &>/dev/null; then
    echo ""
    read -rp "Install as a systemd user service (auto-start on login)? [y/N] " REPLY
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        SERVICE_DIR="$HOME/.config/systemd/user"
        mkdir -p "$SERVICE_DIR"

        # Fill in real paths
        sed \
            -e "s|%h/mcolgan79|$SCRIPT_DIR|g" \
            -e "s|/usr/bin/python3|$(command -v python3)|g" \
            -e "s|your_api_key_here|${ANTHROPIC_API_KEY:-your_api_key_here}|g" \
            "$SCRIPT_DIR/appointment-agent.service" \
            > "$SERVICE_DIR/$SERVICE_NAME.service"

        systemctl --user daemon-reload
        systemctl --user enable "$SERVICE_NAME"
        systemctl --user start "$SERVICE_NAME"
        echo "  ✓ Service installed and started"
        echo "  Logs: journalctl --user -u $SERVICE_NAME -f"
    fi
fi

echo ""
echo "=== Done! ==="
echo ""
echo "Quick start:"
echo "  # Run in foreground (Ctrl+C to stop):"
echo "  python3 $SCRIPT_DIR/cli.py start"
echo ""
echo "  # Or run in background:"
echo "  nohup python3 $SCRIPT_DIR/cli.py start > ~/.appointment_agent/agent.log 2>&1 &"
echo ""
echo "  # Add an appointment:"
echo "  python3 $SCRIPT_DIR/cli.py add-appointment 'Team standup' '2024-06-15 09:00' -l Zoom"
echo ""
echo "  # Add a task:"
echo "  python3 $SCRIPT_DIR/cli.py add-task 'Review PRs' --priority high --due 2024-06-15"
echo ""
echo "  # Run a manual check-in:"
echo "  python3 $SCRIPT_DIR/cli.py checkin morning"
echo ""
echo "  # List everything:"
echo "  python3 $SCRIPT_DIR/cli.py list"
