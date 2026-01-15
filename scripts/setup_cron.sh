#!/bin/bash
# =============================================================================
# Project Sentinel - Crontab Setup Script
# =============================================================================
# This script sets up automated schedule for Sentinel AI
# 
# Schedule:
#   - 11:40 AM (Mon-Fri): Midday Check
#   - 15:10 PM (Mon-Fri): Close Review
# =============================================================================

set -e

# Get project directory
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_PATH="$PROJECT_DIR/.venv/bin/python"

echo "🛡️ Project Sentinel - Crontab Setup"
echo "====================================="
echo "Project Directory: $PROJECT_DIR"
echo "Python Path: $PYTHON_PATH"
echo ""

# Check if python venv exists
if [ ! -f "$PYTHON_PATH" ]; then
    echo "❌ Error: Python venv not found at $PYTHON_PATH"
    echo "   Please create virtual environment first: python3 -m venv .venv"
    exit 1
fi

# Generate crontab entries
MIDDAY_CRON="40 11 * * 1-5 cd $PROJECT_DIR && $PYTHON_PATH -m src.main --mode midday >> $PROJECT_DIR/logs/cron.log 2>&1"
CLOSE_CRON="10 15 * * 1-5 cd $PROJECT_DIR && $PYTHON_PATH -m src.main --mode close >> $PROJECT_DIR/logs/cron.log 2>&1"

echo "📅 Crontab entries to be added:"
echo ""
echo "# Sentinel Midday Check (11:40 AM, Mon-Fri)"
echo "$MIDDAY_CRON"
echo ""
echo "# Sentinel Close Review (15:10 PM, Mon-Fri)"
echo "$CLOSE_CRON"
echo ""

read -p "Do you want to add these entries to crontab? (y/n): " CONFIRM

if [ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ]; then
    # Backup existing crontab
    crontab -l > /tmp/crontab_backup.txt 2>/dev/null || true
    
    # Check if entries already exist
    if grep -q "src.main --mode midday" /tmp/crontab_backup.txt 2>/dev/null; then
        echo "⚠️  Midday entry already exists in crontab"
    else
        (crontab -l 2>/dev/null; echo ""; echo "# Sentinel Midday Check (11:40 AM, Mon-Fri)"; echo "$MIDDAY_CRON") | crontab -
        echo "✅ Midday entry added"
    fi
    
    if grep -q "src.main --mode close" /tmp/crontab_backup.txt 2>/dev/null; then
        echo "⚠️  Close entry already exists in crontab"
    else
        (crontab -l 2>/dev/null; echo ""; echo "# Sentinel Close Review (15:10 PM, Mon-Fri)"; echo "$CLOSE_CRON") | crontab -
        echo "✅ Close entry added"
    fi
    
    echo ""
    echo "🎉 Done! Current crontab:"
    crontab -l | grep -A1 "Sentinel" || echo "(No Sentinel entries found)"
else
    echo "❌ Cancelled. You can manually add the entries above."
fi
