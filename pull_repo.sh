#!/bin/bash

# Change to your project directory
cd /home/ri/stepmom_tv || {
    echo "Failed to enter project directory"
    exit 1
}

# Reset local changes and pull latest from GitHub
git reset --hard
git pull origin main

# Make key scripts executable
chmod +x startup_brain.sh startup_client.sh

echo "Update complete at $(date)" >> /home/ri/update_code.log 