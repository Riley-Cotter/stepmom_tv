#!/bin/bash

/bin/sleep 1; /home/ri/stepmom_tv/mount_usb.sh > /home/ri/mycronlog.txt 2>&1
/bin/sleep 15; /usr/bin/python3 /home/ri/stepmom_tv/background_image.py > /home/ri/mycronlog.txt 2>&1
/bin/sleep 25; /usr/bin/python3 /home/ri/stepmom_tv/video_player_client.py > /home/ri/mycronlog.txt 2>&1