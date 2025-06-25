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

        # IMPROVED VLC STATE MANAGEMENT
        # Force stop any current playback
        player.stop()
        
        # Wait for VLC to fully stop - check multiple states
        print("Waiting for VLC to stop...")
        stop_timeout = 0
        while stop_timeout < 50:  # 5 second timeout
            state = player.get_state()
            if state in [vlc.State.Stopped, vlc.State.Ended, vlc.State.NothingSpecial]:
                break
            print(f"VLC state: {state}, waiting...")
            time.sleep(0.1)
            stop_timeout += 1
        
        if stop_timeout >= 50:
            print("Warning: VLC didn't stop cleanly, continuing anyway")
        else:
            print(f"VLC stopped successfully after {stop_timeout * 0.1:.1f}s")

        # Additional wait for VLC internal cleanup
        time.sleep(0.3)

        # Clear any existing media
        player.set_media(None)
        time.sleep(0.1)

        # Set up new media
        print(f"Loading media: {file_path}")
        media = vlc_instance.media_new(file_path)
        player.set_media(media)
        
        # Wait for media to be set
        time.sleep(0.2)
        
        # Start playback with retry logic
        play_attempts = 0
        play_success = False
        
        while play_attempts < 3 and not play_success:
            play_attempts += 1
            print(f"Play attempt {play_attempts}/3")
            
            result = player.play()
            if result == -1:
                print(f"VLC play() returned error on attempt {play_attempts}")
                time.sleep(0.5)
                continue
                
            # Wait for playback to actually start
            start_timeout = 0
            while start_timeout < 30:  # 3 second timeout
                if player.is_playing():
                    play_success = True
                    break
                time.sleep(0.1)
                start_timeout += 1
            
            if not play_success:
                print(f"Playback didn't start on attempt {play_attempts}")
                if play_attempts < 3:
                    player.stop()
                    time.sleep(0.5)
        
        if not play_success:
            send_acknowledgment(client, command_id, "error", "VLC failed to start playback after 3 attempts")
            with loop_lock:
                looping_enabled = True
            return
        
        print(f"Playback started successfully after {play_attempts} attempts")
        
        # Calculate wait time for synchronized start
        wait_seconds = start_time - time.time()
        if wait_seconds > 0:
            print(f"Waiting {wait_seconds:.2f} seconds for synchronized start...")
            time.sleep(wait_seconds)
        elif wait_seconds < -1:  # If we're more than 1 second late
            print(f"Warning: Starting {abs(wait_seconds):.2f} seconds late")

        # Final verification that we're still playing
        if player.is_playing():
            send_acknowledgment(client, command_id, "success", f"Playing {video_files[index]}")
            print(f"Successfully synchronized and playing: {file_path}")
        else:
            send_acknowledgment(client, command_id, "error", "Playback stopped unexpectedly before sync")
            print("Error: Playback stopped before synchronization")
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
        consecutive_failures = 0
        max_consecutive_failures = 5
        
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
                # IMPROVED LOOPING WITH BETTER VLC HANDLING
                # Stop any current playback cleanly
                if player.is_playing():
                    player.stop()
                    time.sleep(0.2)
                
                # Clear and set new media
                player.set_media(None)
                time.sleep(0.1)
                
                media = vlc_instance.media_new(file_path)
                player.set_media(media)
                time.sleep(0.2)
                
                # Try to start playback
                play_result = player.play()
                if play_result == -1:
                    print("[Loop] VLC play() failed")
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        print(f"[Loop] Too many consecutive failures ({consecutive_failures}), longer wait")
                        time.sleep(10)
                        consecutive_failures = 0
                    else:
                        time.sleep(2)
                    continue
                
                # Wait for playback to start
                start_wait = 0
                while start_wait < 30 and not player.is_playing():
                    time.sleep(0.1)
                    start_wait += 1
                
                if not player.is_playing():
                    print("[Loop] Failed to start playback")
                    consecutive_failures += 1
                    time.sleep(2)
                    continue
                
                # Reset failure counter on success
                consecutive_failures = 0
                print(f"[Loop] Successfully started playback")

                # Monitor playback
                while player.is_playing():
                    # Check if we should stop looping
                    with loop_lock:
                        if not looping_enabled:
                            print("[Loop] Manual video override - stopping loop")
                            break
                    time.sleep(1)

                if looping_enabled:
                    print("[Loop] Video ended naturally, restarting...")
                    time.sleep(0.5)  # Brief pause between loops
                    
            except Exception as e:
                print(f"[Loop] Exception: {e}")
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    print(f"[Loop] Too many failures, waiting longer...")
                    time.sleep(10)
                    consecutive_failures = 0
                else:
                    time.sleep(5)

    global looping_thread
    looping_thread = threading.Thread(target=loop, daemon=True)
    looping_thread.start()
    print("Started improved loop of index 0")

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