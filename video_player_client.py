import os
import time
import threading
import paho.mqtt.client as mqtt
import vlc

# Configuration
VIDEO_DIR = "/media/usb"
MQTT_BROKER = "192.168.50.1"
MQTT_TOPIC_PLAY = "video/play"
MQTT_TOPIC_TIME_REQUEST = "sync/time/request"
MQTT_TOPIC_TIME_RESPONSE = "sync/time"

# Global variables
video_files = []
player = None
vlc_instance = vlc.Instance("--no-audio")
current_index = -1
video_loaded = False
playback_started = False
time_synced = False
brain_time = 0
local_time_at_sync = 0
time_sync_thread = None

def scan_videos():
    global video_files
    exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm')
    video_files = [f for f in sorted(os.listdir(VIDEO_DIR)) if f.lower().endswith(exts)]
    print("[Videos found:]")
    for i, f in enumerate(video_files):
        print(f"  {i}: {f}")

def load_video(index):
    global player, current_index, video_loaded, playback_started

    if index < 0 or index >= len(video_files):
        print(f"[Error] Invalid video index: {index}")
        return

    video_path = os.path.join(VIDEO_DIR, video_files[index])
    print(f"[Load] Loading video: {video_path}")

    if player:
        player.stop()
        del player
        time.sleep(0.5)

    media = vlc_instance.media_new_path(video_path)
    player = vlc_instance.media_player_new()
    player.set_media(media)

    event_manager = player.event_manager()
    event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, on_video_end)

    player.set_pause(1)  # Load and pause
    video_loaded = True
    playback_started = False
    current_index = index

    print("[Load] Video loaded and paused.")

def play_video():
    global player, playback_started

    if not player or playback_started:
        return

    print("[Play] Starting video playback.")
    player.play()
    playback_started = True

def load_and_play_idle():
    load_video(0)
    play_video()

def on_video_end(event):
    global playback_started
    playback_started = False
    print("[End] Video finished.")
    print("[Idle] Playing idle video after any video finished.")
    threading.Timer(1, load_and_play_idle).start()

def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected with result code {rc}")
    client.subscribe(MQTT_TOPIC_PLAY)
    client.subscribe(MQTT_TOPIC_TIME_RESPONSE)

def on_message(client, userdata, msg):
    global time_synced, brain_time, local_time_at_sync

    if msg.topic == MQTT_TOPIC_PLAY:
        try:
            payload = msg.payload.decode()
            index_str, target_time_str = payload.split(',')
            index = int(index_str)
            target_time = float(target_time_str)
            print(f"[MQTT] Received index {index} to play at {target_time} (brain time)")

            if index < 0 or index >= len(video_files):
                print(f"[Error] Invalid index {index} received.")
                return

            load_video(index)

            if time_synced:
                now_local = time.time()
                offset = brain_time - local_time_at_sync
                adjusted_target_time = target_time - offset
                delay = adjusted_target_time - now_local
            else:
                delay = target_time - time.time()

            if delay < 0:
                print(f"[Warning] Scheduled time is in the past. Playing immediately.")
                delay = 0

            print(f"[Info] Will play in {delay:.2f} seconds.")
            threading.Timer(delay, play_video).start()

        except Exception as e:
            print(f"[Error] Invalid MQTT play message or format: {e}")

    elif msg.topic == MQTT_TOPIC_TIME_RESPONSE:
        try:
            brain_time = float(msg.payload.decode())
            local_time_at_sync = time.time()
            time_synced = True
            print(f"[Sync] Time synchronized with brain. Brain time: {brain_time}, Local time at sync: {local_time_at_sync}")
            if time_sync_thread and time_sync_thread.is_alive():
                print("[Sync] Time sync complete. Stopping sync loop.")
        except Exception as e:
            print(f"[Error] Failed to parse brain time: {e}")

def mqtt_loop():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, 1883, 60)
    except Exception as e:
        print(f"[MQTT] Connection error: {e}")
        return

    def time_sync_loop():
        while not time_synced:
            print("[Sync] Requesting time sync from brain...")
            client.publish(MQTT_TOPIC_TIME_REQUEST, "sync")
            time.sleep(5)

    global time_sync_thread
    time_sync_thread = threading.Thread(target=time_sync_loop, daemon=True)
    time_sync_thread.start()

    client.loop_forever()

def main():
    scan_videos()
    print("[Info] Starting MQTT client")
    mqtt_thread = threading.Thread(target=mqtt_loop, daemon=True)
    mqtt_thread.start()

    if len(video_files) > 0:
        print("[Startup] Starting idle video loop (index 0).")
        threading.Timer(1, load_and_play_idle).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Exit] Stopping playback and exiting.")
        if player:
            player.stop()
            del player

if __name__ == "__main__":
    main()
