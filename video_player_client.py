import os
import time
import threading
import paho.mqtt.client as mqtt
import vlc
from datetime import datetime
import uuid
import json
import logging
from typing import Optional, List
from enum import Enum

# Configuration
VIDEO_DIR = "/media/usb"
MQTT_BROKER = "192.168.50.1"
MQTT_TOPIC_PLAY = "video/play"
MQTT_TOPIC_HEARTBEAT = "clients/status"
MQTT_TOPIC_ACK = "video/ack"
MQTT_TOPIC_STATUS = "clients/detailed_status"
HEARTBEAT_INTERVAL = 5  # seconds
CLIENT_ID = str(uuid.getnode())

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/video_client.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PlaybackState(Enum):
    IDLE = "idle"
    LOADING = "loading"
    PLAYING = "playing"
    LOOPING = "looping"
    ERROR = "error"

class VideoClient:
    def __init__(self):
        self.video_files: List[str] = []
        self.vlc_instance = vlc.Instance('--aout=alsa --no-audio --no-video-title')
        
        # CRITICAL FIX: Separate players for different playback types
        self.loop_player: Optional[vlc.MediaPlayer] = None
        self.manual_player: Optional[vlc.MediaPlayer] = None
        self.active_player: Optional[vlc.MediaPlayer] = None  # Track which player is active
        
        # State management
        self.current_state = PlaybackState.IDLE
        self.current_video_index = 0
        self.state_lock = threading.Lock()
        
        # Manual playback control - single source of truth
        self.playback_control_lock = threading.Lock()
        self.manual_mode = False  # True = manual video playing, False = loop mode
        self.manual_transition_time = 0  # When manual mode started
        
        # Loop thread control
        self.looping_thread: Optional[threading.Thread] = None
        self.loop_should_run = True
        self.loop_pause_event = threading.Event()  # Signal to pause loop
        
        # Statistics
        self.stats = {
            'videos_played': 0,
            'loop_cycles': 0,
            'errors': 0,
            'last_error': None,
            'uptime_start': time.time()
        }
        
        # MQTT client
        self.mqtt_client: Optional[mqtt.Client] = None
        self.connected = False
        
    def get_status(self) -> dict:
        """Get detailed client status"""
        with self.state_lock:
            with self.playback_control_lock:
                return {
                    'client_id': CLIENT_ID,
                    'state': self.current_state.value,
                    'video_count': len(self.video_files),
                    'current_video': self.video_files[self.current_video_index] if self.video_files else None,
                    'manual_mode': self.manual_mode,
                    'loop_paused': self.loop_pause_event.is_set(),
                    'active_player': 'manual' if self.active_player == self.manual_player else 'loop' if self.active_player == self.loop_player else 'none',
                    'is_playing': self.active_player.is_playing() if self.active_player else False,
                    'usb_mounted': self.is_usb_mounted(),
                    'uptime': time.time() - self.stats['uptime_start'],
                    'stats': self.stats.copy()
                }
    
    def set_state(self, new_state: PlaybackState):
        """Thread-safe state setting"""
        with self.state_lock:
            if self.current_state != new_state:
                logger.info(f"State change: {self.current_state.value} -> {new_state.value}")
                self.current_state = new_state
    
    def switch_to_manual_mode(self) -> bool:
        """Switch to manual playback mode - stops loop and prepares for manual video"""
        with self.playback_control_lock:
            if self.manual_mode:
                logger.info("Already in manual mode")
                return True
            
            logger.info("=== SWITCHING TO MANUAL MODE ===")
            
            # Step 1: Signal loop to pause
            self.loop_pause_event.set()
            self.manual_transition_time = time.time()
            
            # Step 2: Stop loop player if it's active
            if self.active_player == self.loop_player and self.loop_player:
                logger.info("Stopping loop player for manual override")
                self.loop_player.stop()
                
                # Wait for loop player to stop
                timeout = 0
                while self.loop_player.is_playing() and timeout < 50:  # 5 second timeout
                    time.sleep(0.1)
                    timeout += 1
                
                if self.loop_player.is_playing():
                    logger.warning("Loop player didn't stop cleanly")
                else:
                    logger.info("Loop player stopped successfully")
            
            # Step 3: Switch to manual mode
            self.manual_mode = True
            self.active_player = self.manual_player
            
            logger.info("Manual mode activated")
            return True
    
    def switch_to_loop_mode(self):
        """Switch back to loop mode - stops manual and resumes loop"""
        with self.playback_control_lock:
            if not self.manual_mode:
                logger.info("Already in loop mode")
                return
            
            logger.info("=== SWITCHING TO LOOP MODE ===")
            
            # Step 1: Stop manual player if active
            if self.active_player == self.manual_player and self.manual_player:
                logger.info("Stopping manual player")
                self.manual_player.stop()
                
                # Wait for manual player to stop
                timeout = 0
                while self.manual_player.is_playing() and timeout < 50:
                    time.sleep(0.1)
                    timeout += 1
                
                if self.manual_player.is_playing():
                    logger.warning("Manual player didn't stop cleanly")
                else:
                    logger.info("Manual player stopped successfully")
            
            # Step 2: Switch to loop mode
            self.manual_mode = False
            self.active_player = self.loop_player  
            self.manual_transition_time = 0
            
            # Step 3: Resume loop
            self.loop_pause_event.clear()
            
            logger.info("Loop mode resumed")
    
    def is_in_manual_mode(self) -> tuple[bool, float]:
        """Check if in manual mode and return time since transition"""
        with self.playback_control_lock:
            if not self.manual_mode:
                return False, 0
            
            time_since_transition = time.time() - self.manual_transition_time
            return True, time_since_transition
    
    def send_heartbeat(self):
        """Enhanced heartbeat with status info"""
        while self.connected:
            try:
                # Basic heartbeat
                self.mqtt_client.publish(MQTT_TOPIC_HEARTBEAT, CLIENT_ID)
                
                # Detailed status (less frequent)
                if int(time.time()) % 30 == 0:  # Every 30 seconds
                    status = self.get_status()
                    self.mqtt_client.publish(MQTT_TOPIC_STATUS, json.dumps(status))
                    
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                
            time.sleep(HEARTBEAT_INTERVAL)
    
    def send_acknowledgment(self, command_id: str, status: str, message: str = ""):
        """Send acknowledgment back to brain"""
        try:
            ack_payload = f"{CLIENT_ID}:{command_id}:{status}"
            if message:
                ack_payload += f":{message}"
            self.mqtt_client.publish(MQTT_TOPIC_ACK, ack_payload)
            logger.info(f"Sent ACK: {ack_payload}")
        except Exception as e:
            logger.error(f"Failed to send ACK: {e}")
    
    def is_usb_mounted(self) -> bool:
        """Check if USB is mounted"""
        try:
            with open("/proc/mounts", "r") as mounts:
                return any(VIDEO_DIR in line for line in mounts)
        except Exception as e:
            logger.error(f"Error checking USB mount: {e}")
            return False
    
    def load_video_files(self):
        """Load and sort video files from USB"""
        try:
            if not os.path.exists(VIDEO_DIR):
                logger.warning(f"Video directory {VIDEO_DIR} does not exist")
                return
                
            all_files = os.listdir(VIDEO_DIR)
            self.video_files = sorted([
                f for f in all_files
                if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm'))
            ])
            logger.info(f"Found {len(self.video_files)} videos: {self.video_files}")
            
            # Validate first video for looping
            if self.video_files:
                first_video_path = os.path.join(VIDEO_DIR, self.video_files[0])
                if not os.path.exists(first_video_path):
                    logger.error(f"First video file missing: {first_video_path}")
                    
        except Exception as e:
            logger.error(f"Error loading video files: {e}")
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
    
    def setup_players(self):
        """Initialize separate VLC media players"""
        try:
            # Create separate players for different purposes
            self.loop_player = self.vlc_instance.media_player_new()
            self.manual_player = self.vlc_instance.media_player_new()
            
            # Start in loop mode
            self.active_player = self.loop_player
            
            logger.info("VLC players initialized successfully (loop + manual)")
        except Exception as e:
            logger.error(f"Failed to setup VLC players: {e}")
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
            raise
    
    def start_playback_on_player(self, player: vlc.MediaPlayer, file_path: str, max_attempts: int = 3) -> bool:
        """Start VLC playback on specific player with retry logic"""
        for attempt in range(max_attempts):
            try:
                logger.info(f"Starting playback attempt {attempt + 1}/{max_attempts} on player: {file_path}")
                
                # Clear any existing media
                player.set_media(None)
                time.sleep(0.1)
                
                # Set new media
                media = self.vlc_instance.media_new(file_path)
                player.set_media(media)
                time.sleep(0.2)
                
                # Start playback
                result = player.play()
                if result == -1:
                    logger.warning(f"VLC play() returned error on attempt {attempt + 1}")
                    time.sleep(0.5)
                    continue
                
                # Wait for playback to start
                start_timeout = 0
                while start_timeout < 30:  # 3 second timeout
                    if player.is_playing():
                        logger.info(f"Playback started successfully on attempt {attempt + 1}")
                        return True
                    time.sleep(0.1)
                    start_timeout += 1
                
                logger.warning(f"Playback didn't start on attempt {attempt + 1}")
                if attempt < max_attempts - 1:
                    player.stop()
                    time.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"Playback attempt {attempt + 1} failed: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(0.5)
        
        return False
    
    def play_video(self, index: int, start_time: float, command_id: str):
        """Play a specific video with synchronization"""
        try:
            logger.info(f"=== MANUAL PLAY COMMAND ===")
            logger.info(f"Play command: index={index}, start_time={start_time}, command_id={command_id}")
            
            # Switch to manual mode FIRST - this stops the loop
            if not self.switch_to_manual_mode():
                error_msg = "Failed to switch to manual mode"
                logger.error(error_msg)
                self.send_acknowledgment(command_id, "error", error_msg)
                return
            
            # Give time for mode switch to complete
            time.sleep(1.0)
            
            self.set_state(PlaybackState.LOADING)
            
            # Validate index
            if not (0 <= index < len(self.video_files)):
                error_msg = f"Invalid video index {index} (available: 0-{len(self.video_files)-1})"
                logger.error(error_msg)
                self.send_acknowledgment(command_id, "error", error_msg)
                self.set_state(PlaybackState.ERROR)
                self.switch_to_loop_mode()  # Return to loop mode on error
                return
            
            file_path = os.path.join(VIDEO_DIR, self.video_files[index])
            
            # Check file exists
            if not os.path.exists(file_path):
                error_msg = f"Video file not found: {file_path}"
                logger.error(error_msg)
                self.send_acknowledgment(command_id, "error", error_msg)
                self.set_state(PlaybackState.ERROR)
                self.switch_to_loop_mode()
                return
            
            logger.info(f"Starting manual video on dedicated player: {file_path}")
            
            # Start playback on manual player
            if not self.start_playback_on_player(self.manual_player, file_path):
                error_msg = "Failed to start manual video playback"
                logger.error(error_msg)
                self.send_acknowledgment(command_id, "error", error_msg)
                self.set_state(PlaybackState.ERROR)
                self.switch_to_loop_mode()
                return
            
            # Synchronization
            wait_seconds = start_time - time.time()
            if wait_seconds > 0:
                logger.info(f"Waiting {wait_seconds:.2f}s for synchronization")
                time.sleep(wait_seconds)
            elif wait_seconds < -1:
                logger.warning(f"Starting {abs(wait_seconds):.2f}s late")
            
            # Final verification
            if self.manual_player.is_playing():
                self.set_state(PlaybackState.PLAYING)
                self.current_video_index = index
                self.stats['videos_played'] += 1
                success_msg = f"Playing {self.video_files[index]}"
                self.send_acknowledgment(command_id, "success", success_msg)
                logger.info(f"Manual video synchronized successfully: {file_path}")
            else:
                error_msg = "Manual playback stopped before synchronization"
                logger.error(error_msg)
                self.send_acknowledgment(command_id, "error", error_msg)
                self.set_state(PlaybackState.ERROR)
                self.switch_to_loop_mode()
                return
            
            # Monitor manual playback until finished
            logger.info("=== MONITORING MANUAL PLAYBACK ===")
            playback_start_time = time.time()
            last_log_time = playback_start_time
            
            while self.manual_player.is_playing():
                current_time = time.time()
                
                # Log status every 10 seconds
                if current_time - last_log_time >= 10:
                    elapsed = current_time - playback_start_time
                    logger.info(f"Manual video still playing (elapsed: {elapsed:.1f}s)")
                    last_log_time = current_time
                
                time.sleep(1)
            
            total_elapsed = time.time() - playback_start_time
            logger.info(f"=== MANUAL VIDEO COMPLETED ===")
            logger.info(f"Total playback time: {total_elapsed:.1f}s")
            
            # Return to loop mode
            self.switch_to_loop_mode()
            self.set_state(PlaybackState.LOOPING)
            
            logger.info("Manual playback complete - returning to loop mode")
            
        except Exception as e:
            error_msg = f"Exception in play_video: {str(e)}"
            logger.error(error_msg)
            self.send_acknowledgment(command_id, "error", error_msg)
            self.set_state(PlaybackState.ERROR)
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
            self.switch_to_loop_mode()  # Ensure we return to loop mode
    
    def start_looping(self):
        """Start the looping thread for index 0"""
        def loop_thread():
            consecutive_failures = 0
            max_consecutive_failures = 5
            
            logger.info("=== LOOP THREAD STARTED ===")
            
            while self.loop_should_run:
                try:
                    # Wait if paused (manual mode active)
                    if self.loop_pause_event.is_set():
                        logger.debug("Loop thread paused (manual mode active)")
                        time.sleep(2)
                        continue
                    
                    # Double-check we're not in manual mode
                    in_manual, time_since = self.is_in_manual_mode()
                    if in_manual:
                        logger.debug(f"Loop waiting - manual mode active for {time_since:.1f}s")
                        time.sleep(2)
                        continue
                    
                    # Check if we have videos
                    if not self.video_files:
                        logger.warning("No videos available for looping")
                        time.sleep(5)
                        continue
                    
                    file_path = os.path.join(VIDEO_DIR, self.video_files[0])
                    if not os.path.exists(file_path):
                        logger.error("Loop video (index 0) missing")
                        time.sleep(5)
                        continue
                    
                    logger.info(f"=== STARTING LOOP CYCLE {self.stats['loop_cycles'] + 1} ===")
                    logger.info(f"Loop video: {self.video_files[0]}")
                    
                    self.set_state(PlaybackState.LOOPING)
                    
                    # Start playback on loop player
                    if not self.start_playback_on_player(self.loop_player, file_path):
                        consecutive_failures += 1
                        logger.error(f"Loop playback failed (failure {consecutive_failures})")
                        
                        if consecutive_failures >= max_consecutive_failures:
                            logger.error("Too many consecutive failures, longer wait")
                            time.sleep(10)
                            consecutive_failures = 0
                        else:
                            time.sleep(2)
                        continue
                    
                    # Reset failure counter on success
                    consecutive_failures = 0
                    self.stats['loop_cycles'] += 1
                    logger.info(f"Loop cycle {self.stats['loop_cycles']} started successfully")
                    
                    # Monitor loop playback
                    loop_start_time = time.time()
                    last_check_time = loop_start_time
                    
                    while self.loop_player.is_playing() and self.loop_should_run:
                        # Check if we need to pause for manual mode
                        if self.loop_pause_event.is_set():
                            elapsed = time.time() - loop_start_time
                            logger.info(f"=== MANUAL MODE REQUESTED ===")
                            logger.info(f"Stopping loop after {elapsed:.1f}s")
                            break
                        
                        # Double-check manual mode
                        in_manual, _ = self.is_in_manual_mode()
                        if in_manual:
                            elapsed = time.time() - loop_start_time
                            logger.info(f"=== MANUAL MODE DETECTED ===")
                            logger.info(f"Stopping loop after {elapsed:.1f}s")
                            break
                        
                        # Periodic status logging
                        current_time = time.time()
                        if current_time - last_check_time >= 30:  # Every 30 seconds
                            elapsed = current_time - loop_start_time
                            logger.info(f"Loop video playing (elapsed: {elapsed:.1f}s)")
                            last_check_time = current_time
                        
                        time.sleep(1)
                    
                    # Check if we should restart the loop
                    if not self.loop_pause_event.is_set() and not self.is_in_manual_mode()[0] and self.loop_should_run:
                        total_time = time.time() - loop_start_time
                        logger.info(f"Loop video ended naturally after {total_time:.1f}s, restarting...")
                        time.sleep(1)  # Brief pause before restart
                    else:
                        logger.info("Loop stopped - manual mode active or shutdown requested")
                        
                except Exception as e:
                    consecutive_failures += 1
                    logger.error(f"Loop exception: {e}")
                    self.stats['errors'] += 1
                    self.stats['last_error'] = str(e)
                    
                    if consecutive_failures >= max_consecutive_failures:
                        logger.error("Too many loop failures, extended wait")
                        time.sleep(10)
                        consecutive_failures = 0
                    else:
                        time.sleep(5)
            
            logger.info("Loop thread shutting down")
        
        self.looping_thread = threading.Thread(target=loop_thread, daemon=True)
        self.looping_thread.start()
        logger.info("Started looping thread for index 0")
    
    def on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            logger.info("Connected to MQTT broker")
            self.connected = True
            client.subscribe(MQTT_TOPIC_PLAY)
            
            # Start heartbeat thread
            threading.Thread(target=self.send_heartbeat, daemon=True).start()
        else:
            logger.error(f"MQTT connection failed with code {rc}")
            self.connected = False
    
    def on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        logger.warning(f"Disconnected from MQTT broker (code: {rc})")
        self.connected = False
    
    def on_message(self, client, userdata, msg):
        """MQTT message callback"""
        try:
            payload = msg.payload.decode()
            logger.info(f"Received MQTT message: {payload}")
            
            parts = payload.split(",")
            if len(parts) >= 3:
                index = int(parts[0])
                start_time = float(parts[1])
                command_id = parts[2]
                
                # Process in separate thread
                threading.Thread(
                    target=self.play_video,
                    args=(index, start_time, command_id),
                    daemon=True
                ).start()
            else:
                logger.error(f"Invalid message format: {payload}")
                
        except Exception as e:
            logger.error(f"Error parsing MQTT message: {e}")
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
    
    def wait_for_usb_mount(self, timeout: int = 30) -> bool:
        """Wait for USB to be mounted"""
        logger.info("Waiting for USB mount...")
        start_time = time.time()
        
        while not self.is_usb_mounted():
            if time.time() - start_time > timeout:
                logger.error(f"USB failed to mount after {timeout} seconds")
                return False
            time.sleep(1)
        
        logger.info("USB mounted successfully")
        return True
    
    def run(self):
        """Main client loop"""
        logger.info(f"=== Video Client Starting ===")
        logger.info(f"Client ID: {CLIENT_ID}")
        logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Wait for USB
        if not self.wait_for_usb_mount():
            logger.error("Exiting due to USB mount failure")
            return
        
        # Load videos and setup players
        self.load_video_files()
        self.setup_players()
        
        # Start looping
        self.start_looping()
        
        # Setup MQTT
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_disconnect = self.on_disconnect
        self.mqtt_client.on_message = self.on_message
        
        # Connect to MQTT broker
        try:
            logger.info(f"Connecting to MQTT broker: {MQTT_BROKER}")
            self.mqtt_client.connect(MQTT_BROKER)
            self.mqtt_client.loop_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
        finally:
            self.connected = False
            self.loop_should_run = False
            if self.loop_player:
                self.loop_player.stop()
            if self.manual_player:
                self.manual_player.stop()

def main():
    """Main entry point"""
    try:
        client = VideoClient()
        client.run()
    except Exception as e:
        logger.critical(f"Critical error: {e}")
        raise

if __name__ == "__main__":
    main()