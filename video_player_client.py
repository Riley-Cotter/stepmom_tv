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
        self.player: Optional[vlc.MediaPlayer] = None
        self.vlc_instance = vlc.Instance('--aout=alsa --no-audio --no-video-title')
        
        # State management
        self.current_state = PlaybackState.IDLE
        self.current_video_index = 0
        self.state_lock = threading.Lock()
        
        # Manual playback control - simplified
        self.manual_control_lock = threading.Lock()
        self.manual_playback_active = False
        self.manual_start_time = 0
        
        # Loop thread control
        self.looping_thread: Optional[threading.Thread] = None
        self.loop_should_stop = threading.Event()
        
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
            with self.manual_control_lock:
                return {
                    'client_id': CLIENT_ID,
                    'state': self.current_state.value,
                    'video_count': len(self.video_files),
                    'current_video': self.video_files[self.current_video_index] if self.video_files else None,
                    'manual_playback_active': self.manual_playback_active,
                    'is_playing': self.player.is_playing() if self.player else False,
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
    
    def is_manual_playback_active(self) -> tuple[bool, float]:
        """Check manual playback status - simplified"""
        with self.manual_control_lock:
            if not self.manual_playback_active:
                return False, 0
            
            time_since_start = time.time() - self.manual_start_time
            return True, time_since_start
    
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
                    
        except Exception as e:
            logger.error(f"Error loading video files: {e}")
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
    
    def setup_player(self):
        """Initialize VLC media player"""
        try:
            self.player = self.vlc_instance.media_player_new()
            logger.info("VLC player initialized successfully")
        except Exception as e:
            logger.error(f"Failed to setup VLC player: {e}")
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
            raise
    
    def start_playback_simple(self, file_path: str) -> bool:
        """Start VLC playback - MINIMAL error checking"""
        try:
            logger.info(f"Starting playback: {file_path}")
            
            # Stop current playback if any
            if self.player.is_playing():
                self.player.stop()
                time.sleep(0.2)  # Brief pause
            
            # Set new media and play
            media = self.vlc_instance.media_new(file_path)
            self.player.set_media(media)
            self.player.play()
            
            # Just trust VLC to handle it - no retry logic, no timeout checks
            logger.info("Playback command sent to VLC")
            return True
            
        except Exception as e:
            logger.error(f"Playback failed: {e}")
            return False
    
    def play_video(self, index: int, start_time: float, command_id: str):
        """Play a specific video - SIMPLIFIED"""
        try:
            logger.info(f"=== MANUAL PLAY COMMAND ===")
            logger.info(f"Play command: index={index}, start_time={start_time}, command_id={command_id}")
                        
            # Set manual flags
            with self.manual_control_lock:
                self.manual_playback_active = True
                self.manual_start_time = time.time()
                logger.info("Manual playback control activated")
            
            self.set_state(PlaybackState.LOADING)
            
            # Basic validation only
            if not (0 <= index < len(self.video_files)):
                error_msg = f"Invalid video index {index}"
                logger.error(error_msg)
                self.send_acknowledgment(command_id, "error", error_msg)
                self._reset_manual_flags()
                return
            
            file_path = os.path.join(VIDEO_DIR, self.video_files[index])
            
            if not os.path.exists(file_path):
                error_msg = f"Video file not found: {file_path}"
                logger.error(error_msg)
                self.send_acknowledgment(command_id, "error", error_msg)
                self._reset_manual_flags()
                return
            
            # Start playback - no fancy error handling
            if not self.start_playback_simple(file_path):
                self.send_acknowledgment(command_id, "error", "Failed to start playback")
                self._reset_manual_flags()
                return
            
            # Handle synchronization
            wait_seconds = start_time - time.time()
            if wait_seconds > 0:
                logger.info(f"Waiting {wait_seconds:.2f}s for synchronization")
                time.sleep(wait_seconds)
            elif wait_seconds < -1:
                logger.warning(f"Starting {abs(wait_seconds):.2f}s late")
            
            # Update state and send success
            self.set_state(PlaybackState.PLAYING)
            self.current_video_index = index
            self.stats['videos_played'] += 1
            success_msg = f"Playing {self.video_files[index]}"
            self.send_acknowledgment(command_id, "success", success_msg)
            logger.info(f"Manual video started: {file_path}")
            
            # Simple monitoring - just wait for it to finish, no aggressive checking
            logger.info("Monitoring manual playback...")
            while self.player.is_playing():
                time.sleep(2)  # Check every 2 seconds
            
            logger.info("Manual video finished")
            
            # Reset flags and resume looping
            self._reset_manual_flags()
            self.set_state(PlaybackState.LOOPING)
            
        except Exception as e:
            error_msg = f"Exception in play_video: {str(e)}"
            logger.error(error_msg)
            self.send_acknowledgment(command_id, "error", error_msg)
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
            self._reset_manual_flags()
    
    def _reset_manual_flags(self):
        """Reset manual playback flags"""
        with self.manual_control_lock:
            self.manual_playback_active = False
            self.manual_start_time = 0
            logger.info("Manual playback flags reset")
    
    def start_looping(self):
        """Start the looping thread - SIMPLIFIED"""
        def loop_thread():
            logger.info("=== LOOP THREAD STARTED ===")
            
            while not self.loop_should_stop.is_set():
                try:
                    # Check for manual playback - simplified check
                    manual_active, time_since_start = self.is_manual_playback_active()
                    
                    if manual_active:
                        # Give manual playback some startup time
                        if time_since_start < 5.0:
                            logger.debug("Loop paused - manual video starting")
                        else:
                            logger.debug("Loop paused - manual video active")
                        time.sleep(3)
                        continue
                    
                    # Check if we have videos
                    if not self.video_files:
                        logger.warning("No videos for looping")
                        time.sleep(10)
                        continue
                    
                    file_path = os.path.join(VIDEO_DIR, self.video_files[0])
                    
                    logger.info(f"Starting loop cycle: {self.video_files[0]}")
                    self.set_state(PlaybackState.LOOPING)
                    
                    # Start loop video - no fancy error handling
                    if not self.start_playback_simple(file_path):
                        logger.error("Loop playback failed, retrying in 5s")
                        time.sleep(5)
                        continue
                    
                    # Give VLC a moment to actually start playing
                    time.sleep(1)
                    
                    self.stats['loop_cycles'] += 1
                    logger.info(f"Loop cycle {self.stats['loop_cycles']} started")
                    
                    # Simple monitoring - wait for video to finish OR manual override
                    while self.player.is_playing() and not self.loop_should_stop.is_set():
                        # Check for manual override
                        manual_active, _ = self.is_manual_playback_active()
                        if manual_active:
                            logger.info("Manual override detected - stopping loop")
                            self.player.stop()
                            break
                        
                        time.sleep(2)  # Check every 2 seconds
                    
                    # Only restart if video ended naturally (not due to manual override)
                    manual_active, _ = self.is_manual_playback_active()
                    if not manual_active and not self.loop_should_stop.is_set():
                        logger.info("Loop video ended naturally, restarting...")
                        time.sleep(1)
                    else:
                        logger.info("Loop stopped due to manual override or shutdown")
                        
                except Exception as e:
                    logger.error(f"Loop exception: {e}")
                    self.stats['errors'] += 1
                    self.stats['last_error'] = str(e)
                    time.sleep(5)
            
            logger.info("Loop thread shutting down")
        
        self.looping_thread = threading.Thread(target=loop_thread, daemon=True)
        self.looping_thread.start()
        logger.info("Started looping thread")
    
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
        
        # Load videos and setup player
        self.load_video_files()
        self.setup_player()
        
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
            self.loop_should_stop.set()
            if self.player:
                self.player.stop()

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