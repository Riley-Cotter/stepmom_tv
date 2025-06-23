import os
import time
import paho.mqtt.client as mqtt
import vlc
from datetime import datetime
import threading

VIDEO_DIR = "/media/usb"
MQTT_BROKER = "192.168.50.1"
MQTT_TOPIC_PLAY = "video/play"

video_files = []
player = None
vlc_instance = vlc.Instance('--aout=alsa --no-audio')
looping_disabled_until = 0  # Time until which looping is paused

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

def play_video(index, start_time):
    global player, looping_disabled_until
    if 0 <= index < len(video_files):
        looping_disabled_until = time.time() + 10  # Pause loop for 10 seconds
        file_path = os.path.join(VIDEO_DIR, video_files[index])
        print(f"Preparing to play video {file_path} at {start_time}")
        if player:
            player.stop()
        media = vlc_instance.media_new(file_path)
        player = vlc_instance.media_player_new()
        player.set_media(media)
        player.play()
        time.sleep(0.5)
        wait_seconds = start_time - time.time()
        if wait_seconds > 0:
            print(f"Waiting {wait_seconds:.2f} seconds to start...")
            time.sleep(wait_seconds)
        player.set_pause(0)
        print(f"Started video at {datetime.now()}")
    else:
        print(f"Invalid index {index}, not playing.")

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

def play_looping_index_zero():
    global player
    def loop():
        while True:
            time.sleep(1)
            if time.time() < looping_disabled_until:
                continue
            if not video_files:
                continue
            file_path = os.path.join(VIDEO_DIR, video_files[0])
            print(f"[Loop] Playing {file_path}")
            media = vlc_instance.media_new(file_path)
            player = vlc_instance.media_player_new()
            player.set_media(media)
            player.play()
            time.sleep(1)
            while player.is_playing():
                if time.time() < looping_disabled_until:
                    player.stop()
                    break
                time.sleep(1)
            print("[Loop] Video ended or interrupted, restarting...")

    t = threading.Thread(target=loop, daemon=True)
    t.start()

def main():
    print(f"== Client Startup: {datetime.now().strftime('%c')} ==")
    if not wait_for_usb_mount():
        return
    load_video_files()

    play_looping_index_zero()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER)
    except Exception as e:
        print(f"MQTT connection failed: {e}")
        return

    client.loop_forever()

if __name__ == "__main__":
    main()
