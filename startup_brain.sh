#!/bin/bash

LOG_FILE="/home/ri/mycronlog.txt"
exec >> "$LOG_FILE" 2>&1

echo "== Startup initiated: $(date) =="

# Wait for USB to mount
echo "Waiting for USB mount..."
until [ -d "/media/usb" ] && [ "$(ls -A /media/usb)" ]; do
    echo "  USB not mounted yet..."
    sleep 1
done
/home/ri/stepmom_tv/mount_usb.sh
echo "  USB mounted."

# Wait for background image dependencies (like X server)
until pgrep -f "Xorg" >/dev/null; do
    echo "  Waiting for Xorg to be up..."
    sleep 1
done
/usr/bin/python3 /home/ri/stepmom_tv/background_image.py
echo "  Background image set."

# Pull updates from repo
/home/ri/stepmom_tv/pull_repo.sh
echo "  Repo sync complete."

# Wait for MQTT broker to respond
echo "Waiting for MQTT broker..."
until nc -z 192.168.50.1 1883; do
    echo "  MQTT broker not up..."
    sleep 1
done
echo "  MQTT broker available."

# Start web GUI
/usr/bin/python3 /home/ri/stepmom_tv/web_controller.py &
echo "  Web controller launched."

# Start video brain (scheduling & sync controller)
/usr/bin/python3 /home/ri/stepmom_tv/video_player_brain.py &
echo "  Brain script launched."

# Start video client
echo "  Launching video client script..."
/usr/bin/python3 /home/ri/stepmom_tv/video_player_client.py
echo "  Video client script completed or failed."

echo "== Startup complete: $(date) =="
