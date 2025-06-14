#!/bin/bash

LOGFILE="/home/ri/mycronlog.txt"
exec > "$LOGFILE" 2>&1

echo "== Startup initiated: $(date) =="

# Mount USB
echo "Mounting USB..."
/home/ri/stepmom_tv/mount_usb.sh

# Wait for USB mount to appear at /media/usb
for i in {1..30}; do
    if mount | grep -q "/media/usb"; then
        echo "✅ USB mounted at /media/usb"
        break
    else
        echo "  USB not mounted yet... ($i)"
        sleep 1
    fi
done

if ! mount | grep -q "/media/usb"; then
    echo "❌ USB failed to mount after 30 seconds. Aborting."
    exit 1
fi

# Start background image display
echo "Starting background_image.py..."
python3 /home/ri/stepmom_tv/background_image.py || echo "⚠️ Failed to run background_image.py"

# Pull latest code from GitHub
echo "Pulling latest repo update..."
cd /home/ri/stepmom_tv
git reset --hard
git pull || echo "⚠️ Git pull failed"

# Start web controller
echo "Starting web_controller.py..."
python3 /home/ri/stepmom_tv/web_controller.py &

# Start video brain
echo "Starting video_player_brain.py..."
python3 /home/ri/stepmom_tv/video_player_brain.py &

# Start client
echo "Starting video_player_client.py..."
python3 /home/ri/stepmom_tv/video_player_client.py &

echo "✅ All components launched at: $(date)"
