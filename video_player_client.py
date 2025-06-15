import os
import time
import paho.mqtt.client as mqtt
import vlc
from datetime import datetime

VIDEO_DIR = "/media/usb"
MQTT_BROKER = "192.168.50.1"
MQTT_TOPIC_PLAY = "video/play"

video_files = []
player = None
vlc_instance = vlc.Instance('--aout=alsa --no-audio')
current_index = None

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
    events = player.event_manager()
    events.event_attach(vlc.EventType.MediaPlayerEndReached, on_video_end)

def play_looping_index_zero():
    global player, current_index
    if not video_files:
        print("No videos to play.")
        return

    file_path = os.path.join(VIDEO_DIR, video_files[0])
    print(f"Auto-looping index 0: {file_path}")
    current_index = 0

    media = vlc_instance.media_new(file_path)
    media.add_option('input-repeat=-1')
    player.set_media(media)
    player.play()

def play_video(index, start_time):
    global current_index
    if 0 <= index < len(video_files):
        file_path = os.path.join(VIDEO_DIR, video_files[index])
        print(f"Preparing to play video {file_path} at {start_time}")
        current_index = index

        media = vlc_instance.media_new(file_path)
        player.set_media(media)

        # Ensure any looping stops
        media.add_option('input-repeat=0')

        player.play()
        time.sleep(0.5)
        player.set_pause(1)

        wait_seconds = start_time - time.time()
        if wait_seconds > 0:
            print(f"Waiting {wait_seconds:.2f} seconds to start...")
            time.sleep(wait_seconds)

        player.set_pause(0)
        print(f"Started video at {datetime.now()}")
    else:
        print(f"Invalid video index: {index}")

def on_video_end(event):
    print(f"Video index {current_index} ended")
    if current_index != 0:
        play_looping_index_zero()

def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker")
    client.subscribe(MQTT_TOPIC_PLAY)

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        parts = payload.split(",")
        index = int(parts[0])
        start_time = float(parts[1])
        play_video(index, start_time)
    except Exception as e:
        print(f"Error parsing MQTT message: {msg.payload} - {e}")

def wait_for_usb_mount():
    print("Waiting for USB mount...")
    timeout = 30
    start = time.time()
    while not is_usb_mounted():
        if time.time() - start > timeout:
            print("ERROR: USB failed to mount.")
            return False
        time.sleep(1)
    print("USB mounted.")
    return True

def main():
    print(f"== Client Startup: {datetime.now().strftime('%c')} ==")
    if not wait_for_usb_mount():
        return

    load_video_files()

    setup_player()
    play_looping_index_zero()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER)
        client.loop_forever()
    except Exception as e:
        print(f"MQTT connection failed: {e}")

if __name__ == "__main__":
    main()
