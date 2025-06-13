import os
import time
import paho.mqtt.client as mqtt
import vlc
import threading
import uuid

# Config
VIDEO_DIR = "/media/usb"
MQTT_BROKER = "192.168.50.1"
MQTT_TOPIC_PLAY = "video/play"
MQTT_TOPIC_HEARTBEAT = "clients/status"
HEARTBEAT_INTERVAL = 5  # seconds
PLAY_DELAY = 5          # seconds delay before starting playback after command

VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm', '.mpeg', '.mpg', '.ts')

CLIENT_ID = str(uuid.getnode())  # Use MAC address as unique client ID

video_files = []
player = None
play_lock = threading.Lock()

def update_video_list():
    global video_files
    video_files = sorted(
        [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(VIDEO_EXTENSIONS)]
    )
    print(f"Available videos: {video_files}")

def send_heartbeat(client):
    while True:
        client.publish(MQTT_TOPIC_HEARTBEAT, CLIENT_ID)
        time.sleep(HEARTBEAT_INTERVAL)

def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT Broker")
    client.subscribe(MQTT_TOPIC_PLAY)

def on_message(client, userdata, msg):
    global player
    try:
        index = int(msg.payload.decode())
    except ValueError:
        print("Invalid play command received")
        return

    if index < 0 or index >= len(video_files):
        print("Play command index out of range")
        return

    video_path = os.path.join(VIDEO_DIR, video_files[index])
    print(f"Play command received: {video_files[index]}")

    with play_lock:
        if player:
            player.stop()
        instance = vlc.Instance("--no-audio")
        player = instance.media_player_new()
        media = instance.media_new(video_path)
        player.set_media(media)

        player.play()
        time.sleep(0.1)  # Let VLC load media
        player.pause()
        print("Video cued paused, will start in 5 seconds")

    threading.Thread(target=delayed_play).start()

def delayed_play():
    time.sleep(PLAY_DELAY)
    with play_lock:
        if player:
            print("Starting playback now")
            player.play()

def main():
    update_video_list()
    client = mqtt.Client(client_id=CLIENT_ID)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, 1883, 60)

    heartbeat_thread = threading.Thread(target=send_heartbeat, args=(client,))
    heartbeat_thread.daemon = True
    heartbeat_thread.start()

    client.loop_forever()

if __name__ == "__main__":
    main()
