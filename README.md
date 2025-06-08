1.	For Windows
  a.	Download Ubuntu (Windows Subsystem for Linux)
Raspberry Pi Seutp:
  1.	Install Lite OS (using the raspberry pi imager)
    b.	For Client
      i.	Set Hostname: sub#
      ii.	Include WIFI 
        1.	Username: SweatyBoiz
        2.	Password: mommywifi
    c.	For Brain
      i.	Set Hostname: Brain
      ii.	Include WIFI 
        1.	Username: LocalWIFIUsername
        2.	Password: #LocalPassword
    d.	Enable SSH
  2.	Add Program to Startup
    a.	sudo crontab -e
    b.	For Client
      i.	@reboot /bin/sleep 1; /home/ri/stepmom_tv/startup_client.sh > /home/ri/mycronlog.txt 2>&1
    c.	For Brain
      i.	@reboot /bin/sleep 1; /home/ri/stepmom_tv/startup_brain.sh  > /home/ri/mycronlog.txt 2>&1
  3.	Give Scripts Permission to be Executable
    a.	sudo chmod +x setup
  4.	Run Setup
    a.	sudo ./setup
  5.	Sudo raspi-config
    a.	Navigate to display settings, choose composite
    Test with:  mosquitto_pub -h 192.168.50.1 -t video/request_play -m 2,5
    Server setup on Brain
  6.	For Server: Setup Wifi: https://www.youtube.com/watch?v=rjHz6tXGYxQ
    a.	sudo apt install iptables
    b.	sudo update-alternatives --set iptables /usr/sbin/iptables-legacy
    c.	sudo update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy
    d.	curl -sL https://install.raspap.com | bash
      i.	Yes for Everything (except I didn’t)
    e.	Sudo reboot
    f.	sudo systemctl status hostapd
    g.	sudo systemctl status dnsmasq
    h.	Open Browser
      i.	Type Raspberrypi Ip into web address field
        1.	admin
        2.	passkey secret
      ii.	HotSpot
        1.	uap0
        2.	SSID: SweatyBoiz
        3.	802.11g - 2.4 GHz
        4.	Channel: 1
        5.	WPA2
        6.	CCMP
        7.	PSK: mommywifi
        8.	Brideged AP mode: OFF
        9.	WiFi client AP mode: ON
        10.	Hide SSID in broadcast: OFF
        11.	Beacon interval: 100
        12.	Auto
        13.	200
        14.	US
      iii.	Save and Restart
        1.	Should have 3 solid green circles up top.
