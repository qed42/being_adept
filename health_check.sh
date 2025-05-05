#!/bin/bash
# health_check.sh - Script to verify the Slack bot is running correctly

# Check if systemd service is active
if ! systemctl is-active --quiet being-adept-slack-bot; then
  echo "ERROR: being-adept-slack-bot service is not running"
  systemctl status being-adept-slack-bot --no-pager
  exit 1
fi

# Check if the process exists
BOT_PID=$(pgrep -f "python app.py")
if [ -z "$BOT_PID" ]; then
  echo "ERROR: No process found running app.py"
  exit 1
fi

# Check recent logs for errors
if grep -q "ERROR\|Exception\|Traceback" /var/log/syslog | grep "being-adept-slack-bot" | tail -n 20; then
  echo "WARNING: Found error messages in recent logs"
  # Don't exit with error as the service might still be functioning
fi

echo "Health check passed: Slack bot is running properly"
exit 0
