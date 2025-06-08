#!/bin/bash

sudo apt -y update
sudo apt -y upgrade
sudo apt install -y python3-pip
sudo apt-get install -y vlc
sudo sed -i 's/geteuid/getppid/' /usr/bin/vlc
sudo apt-get install -y fbi
sudo apt-get install -y mosquito
sudo apt-get install -y mosquito-clients
sudo apt install -y python3-paho-mqtt
sudo apt install -y python3-vlc
sudo apt install -y python3-flask

#Set code to executable
sudo chmod +x /home/ri/stepmom_tv/startup_client*
sudo chmod +x /home/ri/stepmom_tv/startup_brain*
sudo chmod +x /home/ri/stepmom_tv/background_image*
sudo chmod +x /home/ri/stepmom_tv/video_player_brain*
sudo chmod +x /home/ri/stepmom_tv/video_player_client*
sudo chmod +x /home/ri/stepmom_tv/web_controller*

echo "[✔] Setup Complete"
