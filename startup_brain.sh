#!/bin/bash

LOG_FILE="/home/ri/mycronlog.txt"
echo -e "\n== Startup initiated: $(date) ==" >> "$LOG_FILE"

# Mount USB
/bin/sleep 1
echo -e "Start USB MOUNT" >> "$LOG_FILE"
/home/ri/stepmom_tv/mount_usb.sh >> "$LOG_FILE" 2>&1 &

# Start background image script
/bin/sleep 10
echo -e "Start Background Image" >> "$LOG_FILE"
/usr/bin/python3 /home/ri/stepmom_tv/background_image.py >> "$LOG_FILE" 2>&1 &

# Pull latest repo update
/bin/sleep 15
echo -e "Pull Repo" >> "$LOG_FILE"
/home/ri/stepmom_tv/pull_repo.sh >> "$LOG_FILE" 2>&1 &

# Start web controller
# /bin/sleep 25
# echo -e "Start Web Controller" >> "$LOG_FILE"
# /usr/bin/python3 /home/ri/stepmom_tv/web_controller.py >> "$LOG_FILE" 2>&1 &

# Start video player client
/bin/sleep 30
echo -e "Start Video Player Cleint" >> "$LOG_FILE"
/usr/bin/python3 /home/ri/stepmom_tv/video_player_client.py >> "$LOG_FILE" 2>&1 &

# Start video player brain
/bin/sleep 35
echo -e "Start Video Player Brain" >> "$LOG_FILE"
/usr/bin/python3 /home/ri/stepmom_tv/video_player_brain.py >> "$LOG_FILE" 2>&1 &

# Optional: keep script alive to prevent service from exiting (if needed)
wait