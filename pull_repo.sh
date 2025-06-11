#!/bin/bash

REPO_DIR="/home/ri/stepmom_tv"

# Add repo as a safe Git directory (prevents "dubious ownership" error)
git config --global --add safe.directory "$REPO_DIR"

# Change to repo directory
cd "$REPO_DIR" || {
    echo "Failed to enter project directory: $REPO_DIR"
    exit 1
}

# Reset local changes and pull latest code
git reset --hard
git pull origin main

# Make key scripts executable
chmod +x *.sh

# Log completion
echo "Update complete at $(date)" >> /home/ri/update_code.log
