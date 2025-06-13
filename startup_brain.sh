#!/bin/bash

/bin/sleep 1; /home/ri/stepmom_tv/mount_usb.sh > /home/ri/mycronlog.txt 2>&1
/bin/sleep 3; /usr/bin/python3 /home/ri/stepmom_tv/background_image.py >> /home/ri/mycronlog.txt 2>&1
/bin/sleep 10; /home/ri/stepmom_tv/pull_repo.sh >> /home/ri/mycronlog.txt 2>&1
#/bin/sleep 13; /usr/bin/python3 /home/ri/stepmom_tv/video_player_brain.py >> /home/ri/mycronlog.txt 2>&1
/bin/sleep 15; /usr/bin/python3 /home/ri/stepmom_tv/video_player_client.py >> /home/ri/mycronlog.txt 2>&1
/bin/sleep 20; /usr/bin/python3 /home/ri/stepmom_tv/web_controller.py >> /home/ri/mycronlog.txt 2>&1