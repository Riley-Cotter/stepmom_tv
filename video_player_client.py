import os
import time
import threading
import paho.mqtt.client as mqtt
import vlc
from datetime import datetime
import uuid

VIDEO_DIR = "/media/usb"
MQTT_BROKER = "192.168.50.1"
MQTT_TOPIC_PLAY = "video/play"
MQTT_TOPIC_HEARTBEAT = "clients/status"
HEARTBEAT_INTERVAL = 5  # seconds

# Generate a unique client ID (or use hostname)
CLIENT_ID = str(uuid.getnode())  # MAC address as ID

video_files = []
player = None
vlc_instance = vlc.Instance('--aout=alsa --no-audio')

def send_heartbeat(client):
    while True:
        client.publish(MQTT_TOPIC_HEARTBEAT, CLIENT_ID)
        time.sleep(HEARTBEAT_INTERVAL)

def is_usb_mounted():
    try:
        with open("/proc/mounts", "r") as mounts:
            return any(VIDEO_DIR in line for line in mounts)
    except Exception:
        return False

def load_video_files():
    global video_files
    video_files = sorted([
        f for f in os.listdir(VIDEO_DIR)
        if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv'))
    ])
    print(f"Found videos: {video_files}")

def setup_player():
    global player
    player = vlc_instance.media_player_new()
    print("Player setup complete")

def play_video(index, start_time):
    global player
    if 0 <= index < len(video_files):
        file_path = os.path.join(VIDEO_DIR, video_files[index])
        print(f"Preparing to play video {file_path} at {start_time}")
        if player:
            player.stop()
        media = vlc_instance.media_new(file_path)
        player.set_media(media)
        player.play()
        time.sleep(0.5)
        wait_seconds = start_time - time.time()
        if wait_seconds > 0:
            print(f"Waiting {wait_seconds:.2f} seconds to start...")
            time.sleep(wait_seconds)
        print(f"Playing video: {file_path}")
    else:
        print(f"Invalid index {index}, not playing.")

def play_looping_index_zero():
    global player
    if len(video_files) == 0:
        print("No videos to play.")
        return

    if not (os.path.exists(os.path.join(VIDEO_DIR, video_files[0]))):
        print("Index 0 video missing.")
        return

    def loop():
        while True:
            file_path = os.path.join(VIDEO_DIR, video_files[0])
            print(f"[Loop] Playing {file_path}")
            media = vlc_instance.media_new(file_path)
            player.set_media(media)
            player.play()
            time.sleep(1)

            # Wait for video to finish
            while player.is_playing():
                time.sleep(1)
            print("[Loop] Video ended, restarting...")

    threading.Thread(target=loop, daemon=True).start()
    print("Started loop of index 0")

def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT Broker")
    client.subscribe(MQTT_TOPIC_PLAY)

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        parts = payload.split(",")
        index = int(parts[0])
        start_time = float(parts[1])
        play_video(index, start_time)
    except Exception as e:
        print(f"Error parsing message: {msg.payload}, {e}")

def wait_for_usb_mount():
    print("Waiting for USB mount...")
    timeout = 30
    start = time.time()
    while not is_usb_mounted():
        if time.time() - start > timeout:
            print("ERROR: USB failed to mount after 30 seconds.")
            return False
        print("  USB not mounted yet...")
        time.sleep(1)
    print("USB is mounted.")
    return True

def main():
    print(f"== Client Startup: {datetime.now().strftime('%c')} ==")

    if not wait_for_usb_mount():
        print("Exiting due to missing USB")
        return

    load_video_files()
    setup_player()
    play_looping_index_zero()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER)
        print("MQTT connect successful")
        client.loop_forever()
    except Exception as e:
        print(f"MQTT connection failed: {e}")

if __name__ == "__main__":
    main()