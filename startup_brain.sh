#!/bin/bash

LOG_FILE="/home/ri/mycronlog.txt"
echo -e "\n== Startup initiated: $(date) ==" > "$LOG_FILE"

# Mount USB
echo -e "Start USB MOUNT" >> "$LOG_FILE"
/home/ri/stepmom_tv/mount_usb.sh >> "$LOG_FILE" 2>&1 &

# Start background image script
echo -e "Start Background Image" >> "$LOG_FILE"
/usr/bin/python3 /home/ri/stepmom_tv/background_image.py >> "$LOG_FILE" 2>&1 &

# Pull latest repo update
/bin/sleep 3
echo -e "Pull Repo" >> "$LOG_FILE"
/home/ri/stepmom_tv/pull_repo.sh >> "$LOG_FILE" 2>&1 

# Start video player client
/bin/sleep 2
echo -e "Start Video Player Client" >> "$LOG_FILE"
/usr/bin/python3 /home/ri/stepmom_tv/video_player_client.py >> "$LOG_FILE" 2>&1 &

# Start video player brain
/bin/sleep 5
echo -e "Start Video Player Brain" >> "$LOG_FILE"
/usr/bin/python3 /home/ri/stepmom_tv/video_player_brain.py >> "$LOG_FILE" 2>&1 &

# Optional: keep script alive to prevent service from exiting (if needed)
wait