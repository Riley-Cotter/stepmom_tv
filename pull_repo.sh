#!/bin/bash

REPO_DIR="/home/ri/stepmom_tv"
LOG_FILE="/home/ri/mycronlog.txt"

echo -e "\n== Repo Update Started: $(date) ==" >> "$LOG_FILE"

# Check for internet connectivity
if ping -c 1 github.com &> /dev/null; then
    echo "✅ Internet connection detected. Proceeding with repo update..." >> "$LOG_FILE"

    # Add repo as safe directory
    git config --global --add safe.directory "$REPO_DIR"

    # Change to repo directory
    cd "$REPO_DIR" || {
        echo "❌ Failed to enter project directory: $REPO_DIR" >> "$LOG_FILE"
        exit 1
    }

    # Reset and pull
    git reset --hard >> "$LOG_FILE" 2>&1
    git pull origin main >> "$LOG_FILE" 2>&1

    # Make scripts executable
    chmod +x *.sh

    echo "✅ Update complete at $(date)" >> "$LOG_FILE"
else
    echo "⚠️ No internet connection. Skipping repo update." >> "$LOG_FILE"
fi
