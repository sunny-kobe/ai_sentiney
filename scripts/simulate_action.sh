#!/bin/bash
# Simulating GitHub Action Step: Run Sentinel

# Load .env variables for local run (GitHub Actions uses 'secrets' context)
if [ -f .env ]; then
  export $(cat .env | xargs)
fi

# Get current UTC hour
current_hour=$(date -u +%H)
echo "-------------------------------------------"
echo "Current Local Time: $(date)"
echo "Current UTC Hour:   $current_hour"
echo "-------------------------------------------"

# Mocking the schedule logic from daily_sentinel.yml
# 11:40 CST (Midday) is 03:40 UTC.
# 15:10 CST (Close) is 07:10 UTC.
# The Action runs based on Cron, but the script logic checks hour to decide MODE.
# "if [ "$current_hour" -lt 6 ]; then ... midday ... else ... close ..."

if [ "$current_hour" -lt 6 ]; then
  echo ">>> [Logic Branch] Hour < 6: Running MIDDAY Check"
  ./.venv/bin/python -m src.main --mode midday --dry-run
else
  echo ">>> [Logic Branch] Hour >= 6: Running CLOSE Review"
  ./.venv/bin/python -m src.main --mode close --dry-run
fi
