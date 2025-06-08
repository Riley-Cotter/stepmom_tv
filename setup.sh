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

#Copy Code to RaspberryPi
sudo scp /media/usb/startup_client* /home/ri/
sudo scp /media/usb/startup_brain* /home/ri/
sudo scp /media/usb/background_image* /home/ri/
sudo scp /media/usb/video_player_brain* /home/ri/
sudo scp /media/usb/video_player_client* /home/ri/
sudo scp /media/usb/web_controller* /home/ri/

#Set code to executable
sudo chmod +x startup_client*
sudo chmod +x startup_brain*
sudo chmod +x background_image*
sudo chmod +x video_player_brain*
sudo chmod +x video_player_client*
sudo chmod +x web_controller*

# Create templates directory
mkdir -p templates

# Create index.html 
sudo scp /media/usb/index* /home/ri/templates/


echo "[✔] Setup Complete"
