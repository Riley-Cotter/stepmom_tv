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
MQTT_TOPIC_ACK = "video/ack"
HEARTBEAT_INTERVAL = 5  # seconds

CLIENT_ID = str(uuid.getnode())

video_files = []
player = None
vlc_instance = vlc.Instance('--aout=alsa --no-audio')

looping_enabled = True
looping_thread = None
loop_lock = threading.Lock()

def send_heartbeat(client):
    while True:
        client.publish(MQTT_TOPIC_HEARTBEAT, CLIENT_ID)
        time.sleep(HEARTBEAT_INTERVAL)

def send_acknowledgment(client, command_id, status, message=""):
    """Send acknowledgment back to brain"""
    ack_payload = f"{CLIENT_ID}:{command_id}:{status}"
    if message:
        ack_payload += f":{message}"
    client.publish(MQTT_TOPIC_ACK, ack_payload)
    print(f"Sent ACK: {ack_payload}")

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

def play_video(client, index, start_time, command_id):
    global looping_enabled

    try:
        print(f"Received play command: index={index}, start_time={start_time}, command_id={command_id}")
        
        # Validate index
        if not (0 <= index < len(video_files)):
            send_acknowledgment(client, command_id, "error", f"Invalid index {index}")
            return
        
        file_path = os.path.join(VIDEO_DIR, video_files[index])
        
        # Check if file exists
        if not os.path.exists(file_path):
            send_acknowledgment(client, command_id, "error", f"File not found: {file_path}")
            return

        with loop_lock:
            looping_enabled = False  # disable looping temporarily

        print(f"Preparing to play video {file_path} at {start_time}")

        # Stop current playback more gracefully
        if player.is_playing():
            player.stop()
            # Wait for VLC to actually stop
            timeout = 0
            while player.get_state() == vlc.State.Playing and timeout < 20:
                time.sleep(0.1)
                timeout += 1
            
            if timeout >= 20:
                print("Warning: Player took too long to stop")

        # Set up new media
        media = vlc_instance.media_new(file_path)
        player.set_media(media)
        
        # Give VLC time to prepare
        time.sleep(0.2)
        
        # Start playback
        result = player.play()
        if result == -1:
            send_acknowledgment(client, command_id, "error", "VLC play() failed")
            with loop_lock:
                looping_enabled = True
            return
        
        # Wait a moment for playback to actually start
        time.sleep(0.5)
        
        # Calculate wait time for synchronized start
        wait_seconds = start_time - time.time()
        if wait_seconds > 0:
            print(f"Waiting {wait_seconds:.2f} seconds to start synchronized...")
            time.sleep(wait_seconds)
        elif wait_seconds < -1:  # If we're more than 1 second late
            print(f"Warning: Starting {abs(wait_seconds):.2f} seconds late")

        # Verify playback started successfully
        if player.is_playing():
            send_acknowledgment(client, command_id, "success", f"Playing {video_files[index]}")
            print(f"Successfully started playing: {file_path}")
        else:
            send_acknowledgment(client, command_id, "error", "Playback failed to start")
            print("Error: Playback failed to start")
            with loop_lock:
                looping_enabled = True
            return

        # Monitor playback
        while player.is_playing():
            time.sleep(1)

        print("Manual video finished. Resuming loop...")
        time.sleep(1)

        with loop_lock:
            looping_enabled = True  # allow loop again

    except Exception as e:
        error_msg = f"Exception in play_video: {str(e)}"
        print(error_msg)
        send_acknowledgment(client, command_id, "error", error_msg)
        with loop_lock:
            looping_enabled = True

def play_looping_index_zero():
    def loop():
        global looping_enabled
        while True:
            with loop_lock:
                if not looping_enabled:
                    time.sleep(1)
                    continue

            if len(video_files) == 0:
                print("[Loop] No videos to play.")
                time.sleep(5)
                continue

            file_path = os.path.join(VIDEO_DIR, video_files[0])
            if not os.path.exists(file_path):
                print("[Loop] Index 0 video missing.")
                time.sleep(5)
                continue

            print(f"[Loop] Playing {file_path}")
            
            try:
                media = vlc_instance.media_new(file_path)
                player.set_media(media)
                player.play()
                time.sleep(1)

                while player.is_playing():
                    # Check if we should stop looping
                    with loop_lock:
                        if not looping_enabled:
                            break
                    time.sleep(1)

                if looping_enabled:
                    print("[Loop] Video ended, restarting...")
                else:
                    print("[Loop] Stopping loop for manual video")
                    
            except Exception as e:
                print(f"[Loop] Error playing video: {e}")
                time.sleep(5)

    global looping_thread
    looping_thread = threading.Thread(target=loop, daemon=True)
    looping_thread.start()
    print("Started loop of index 0")

def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT Broker")
    client.subscribe(MQTT_TOPIC_PLAY)
    threading.Thread(target=send_heartbeat, args=(client,), daemon=True).start()

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        print(f"Received MQTT message: {payload}")
        
        parts = payload.split(",")
        if len(parts) >= 3:
            index = int(parts[0])
            start_time = float(parts[1])
            command_id = parts[2]
            
            # Process command in separate thread to avoid blocking MQTT
            threading.Thread(
                target=play_video, 
                args=(client, index, start_time, command_id), 
                daemon=True
            ).start()
        else:
            print(f"Invalid message format: {payload}")
            
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
    print(f"Client ID: {CLIENT_ID}")

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