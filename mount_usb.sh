#!/bin/bash

#Pause to let Raspberrpi Startup
sleep 10

# Create mount point if it doesn't exist
MOUNT_POINT="/media/usb"
/usr/bin/sudo /bin/mkdir -p "$MOUNT_POINT"

# Find the USB device (assumes first partition on first external drive)
DEVICE="/dev/sda1"

# Exit if no USB found
if [ ! -b "$DEVICE" ]; then
        echo "No USB stick detected at $DEVICE."
        exit 1
else
        echo "USB Stick Successfully mounted"
fi

# Mount it
/usr/bin/sudo /bin/mount "$DEVICE" "$MOUNT_POINT"


