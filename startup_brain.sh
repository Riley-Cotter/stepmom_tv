#!/bin/bash

LOGFILE="/home/ri/mycronlog.txt"
echo "== Startup initiated: $(date) ==" > "$LOGFILE"

# Run mount_usb.sh
/home/ri/stepmom_tv/mount_usb.sh >> "$LOGFILE" 2>&1

# Show background image
/usr/bin/python3 /home/ri/stepmom_tv/background_image.py >> "$LOGFILE" 2>&1

# Pull latest repo code
/home/ri/stepmom_tv/pull_repo.sh >> "$LOGFILE" 2>&1

# Launch Flask web controller in background
/usr/bin/python3 /home/ri/stepmom_tv/web_controller.py >> "$LOGFILE" 2>&1 &

# Launch brain video player in background
/usr/bin/python3 /home/ri/stepmom_tv/video_player_brain.py >> "$LOGFILE" 2>&1 &

# Launch client video player in background
/usr/bin/python3 /home/ri/stepmom_tv/video_player_client.py >> "$LOGFILE" 2>&1 &
