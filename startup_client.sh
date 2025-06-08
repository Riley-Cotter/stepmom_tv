#!/bin/bash

/bin/sleep 1; /home/ri/mount_usb > /home/ri/mycronlog.txt 2>&1
/bin/sleep 15; /usr/bin/python3 /home/ri/background_image.py > /home/ri/mycronlog.txt 2>&1
/bin/sleep 25; /usr/bin/python3 /home/ri/video_player_client.py > /home/ri/mycronlog.txt 2>&1