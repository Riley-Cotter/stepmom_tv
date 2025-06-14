#!/bin/bash

LOGFILE="/home/ri/mycronlog.txt"
echo "== Startup initiated: $(date) ==" > "$LOGFILE"

log_and_exit_on_failure() {
    if [ $1 -ne 0 ]; then
        echo "ERROR: $2 failed with exit code $1" >> "$LOGFILE"
        exit $1
    else
        echo "SUCCESS: $2 completed" >> "$LOGFILE"
    fi
}

# === Wait for USB to be mounted ===
echo "Waiting for USB mount..." >> "$LOGFILE"
for i in {1..30}; do
    if grep -qs '/media/usb ' /proc/mounts; then
        echo "USB Stick Successfully mounted" >> "$LOGFILE"
        break
    else
        echo "  USB not mounted yet... ($i)" >> "$LOGFILE"
        sleep 1
    fi

    if [ "$i" -eq 30 ]; then
        echo "ERROR: USB failed to mount after 30 seconds" >> "$LOGFILE"
        exit 1
    fi
done

# === Run mount_usb.sh ===
/home/ri/stepmom_tv/mount_usb.sh >> "$LOGFILE" 2>&1
log_and_exit_on_failure $? "mount_usb.sh"

# === Run background_image.py ===
/usr/bin/python3 /home/ri/stepmom_tv/background_image.py >> "$LOGFILE" 2>&1
log_and_exit_on_failure $? "background_image.py"

# === Pull latest repo code ===
/home/ri/stepmom_tv/pull_repo.sh >> "$LOGFILE" 2>&1
log_and_exit_on_failure $? "pull_repo.sh"

# === Launch web_controller.py ===
/usr/bin/python3 /home/ri/stepmom_tv/web_controller.py >> "$LOGFILE" 2>&1 &
if [ $? -eq 0 ]; then
    echo "SUCCESS: web_controller.py launched" >> "$LOGFILE"
else
    echo "ERROR: Failed to start web_controller.py" >> "$LOGFILE"
    exit 1
fi

# === Launch video_player_brain.py ===
/usr/bin/python3 /home/ri/stepmom_tv/video_player_brain.py >> "$LOGFILE" 2>&1 &
if [ $? -eq 0 ]; then
    echo "SUCCESS: video_player_brain.py launched" >> "$LOGFILE"
else
    echo "ERROR: Failed to start video_player_brain.py" >> "$LOGFILE"
    exit 1
fi

# === Launch video_player_client.py ===
/usr/bin/python3 /home/ri/stepmom_tv/video_player_client.py >> "$LOGFILE" 2>&1 &
if [ $? -eq 0 ]; then
    echo "SUCCESS: video_player_client.py launched" >> "$LOGFILE"
else
    echo "ERROR: Failed to start video_player_client.py" >> "$LOGFILE"
    exit 1
fi
