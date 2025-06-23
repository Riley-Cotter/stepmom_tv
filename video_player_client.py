import os
import time
import threading
import paho.mqtt.client as mqtt
import vlc
from datetime import datetime

VIDEO_DIR = "/media/usb"
MQTT_BROKER = "192.168.50.1"
MQTT_TOPIC_PLAY = "video/play"

video_files = []
player = None
vlc_instance = vlc.Instance('--aout=alsa --no-audio')

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

player_lock = threading.Lock()

def play_video(index, start_time):
    global looping_enabled

    if 0 <= index < len(video_files):
        with loop_lock:
            looping_enabled = False  # pause looping

        with player_lock:
            file_path = os.path.join(VIDEO_DIR, video_files[index])
            print(f"Preparing to play video {file_path} at {start_time}")

            player.stop()
            time.sleep(0.3)  # give VLC time to fully stop

            media = vlc_instance.media_new(file_path)
            player.set_media(media)
            player.play()

            # Wait for player to initialize
            for _ in range(20):  # wait up to 2 seconds
                if player.is_playing():
                    break
                time.sleep(0.1)

            wait_seconds = start_time - time.time()
            if wait_seconds > 0:
                print(f"Waiting {wait_seconds:.2f} seconds to start...")
                time.sleep(wait_seconds)

            print(f"Playing video: {file_path}")
            while player.is_playing():
                time.sleep(0.5)

        print("Manual video finished. Resuming loop...")
        time.sleep(0.5)

        with loop_lock:
            looping_enabled = True
    else:
        print(f"Invalid index {index}, not playing.")

def play_looping_index_zero():
    def loop():
        global looping_enabled
        while True:
            with loop_lock:
                if not looping_enabled:
                    time.sleep(1)
                    continue

            if len(video_files) == 0:
                time.sleep(5)
                continue

            file_path = os.path.join(VIDEO_DIR, video_files[0])
            if not os.path.exists(file_path):
                time.sleep(5)
                continue

            with player_lock:
                print(f"[Loop] Playing {file_path}")
                player.stop()
                time.sleep(0.3)

                media = vlc_instance.media_new(file_path)
                player.set_media(media)
                player.play()

                # Wait for video to start
                for _ in range(20):
                    if player.is_playing():
                        break
                    time.sleep(0.1)

                while player.is_playing():
                    time.sleep(1)

                print("[Loop] Video ended, restarting...")

    global looping_thread
    looping_thread = threading.Thread(target=loop, daemon=True)
    looping_thread.start()


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