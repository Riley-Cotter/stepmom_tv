#!/bin/bash

/bin/sleep 1; /home/ri/mount_usb > /home/ri/mycronlog.txt 2>&1
/bin/sleep 15; /usr/bin/python3 /home/ri/background_image > /home/ri/mycronlog.txt 2>&1
/bin/sleep 20; /usr/bin/python3 /home/ri/video_player_brain > /home/ri/mycronlog.txt 2>&1
/bin/sleep 25; /usr/bin/python3 /home/ri/video_player_client > /home/ri/mycronlog.txt 2>&1
/bin/sleep 30; /usr/bin/python3 /home/ri/web_controller > /home/ri/mycronlog.txt 2>&1