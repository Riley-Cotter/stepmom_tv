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
looping = True  # Global flag to control looping thread

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

def loop_video(index=0):
    global player, looping
    if not (0 <= index < len(video_files)):
        print("Loop video index out of range.")
        return

    file_path = os.path.join(VIDEO_DIR, video_files[index])
    print(f"Starting loop playback of {file_path}")

    while looping:
        media = vlc_instance.media_new(file_path)
        player = vlc_instance.media_player_new()
        player.set_media(media)
        player.play()

        while player.get_state() not in (vlc.State.Ended, vlc.State.Error):
            if not looping:
                player.stop()
                return
            time.sleep(0.2)

        time.sleep(0.5)

def play_video(index, start_time):
    global player, looping

    # Stop looping
    looping = False
    time.sleep(0.2)

    if 0 <= index < len(video_files):
        file_path = os.path.join(VIDEO_DIR, video_files[index])
        print(f"Preparing to play video {file_path} at {start_time}")
        if player:
            player.stop()
        media = vlc_instance.media_new(file_path)
        player = vlc_instance.media_player_new()
        player.set_media(media)
        player.play()
        time.sleep(0.5)
        player.set_pause(1)
        wait_seconds = start_time - time.time()
        if wait_seconds > 0:
            print(f"Waiting {wait_seconds:.2f} seconds to start...")
            time.sleep(wait_seconds)
        player.set_pause(0)
        print(f"Started video at {datetime.now()}")

        # Wait for video to end
        while player.get_state() not in (vlc.State.Ended, vlc.State.Error):
            time.sleep(0.2)

        print("Scheduled video ended. Resuming loop...")
        looping = True
        threading.Thread(target=loop_video, daemon=True).start()
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

def main():
    print(f"== Client Startup: {datetime.now().strftime('%c')} ==")
    if not wait_for_usb_mount():
        return
    load_video_files()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER)
    except Exception as e:
        print(f"MQTT connection failed: {e}")
        return

    client.loop_start()  # Background MQTT loop

    # Start default looping video (index 0)
    threading.Thread(target=loop_video, daemon=True).start()

    # Keep main thread alive
    while True:
        time.sleep(10)

if __name__ == "__main__":
    main()
