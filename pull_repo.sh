#!/bin/bash

REPO_DIR="/home/ri/stepmom_tv"
LOG_FILE="/home/ri/mycronlog.txt"

# Function to check internet connectivity by pinging Google DNS
wait_for_internet() {
    echo "Checking internet connectivity..."
    while ! ping -c 1 -W 1 8.8.8.8 &> /dev/null; do
        echo "$(date): No internet connection. Waiting 5 seconds..." >> "$LOG_FILE"
        sleep 5
    done
    echo "$(date): Internet connection detected." >> "$LOG_FILE"
}

# Add repo as a safe Git directory (prevents "dubious ownership" error)
git config --global --add safe.directory "$REPO_DIR"

# Wait for internet before pulling
wait_for_internet

# Change to repo directory
cd "$REPO_DIR" || {
    echo "Failed to enter project directory: $REPO_DIR" >> "$LOG_FILE"
    exit 1
}

# Reset local changes and pull latest code
git reset --hard
git pull origin branch2

# Make key scripts executable
chmod +x *.sh

# Log completion
echo "Update complete at $(date)" >> "$LOG_FILE" 2>&1
