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
sudo apt install -y python3-flasksudo
sudo apt install -y mosquitto-clients

#Set shell scripts code to executable
chmod +x /home/ri/stepmom_tv/*.sh

echo "[✔] Setup Complete"
