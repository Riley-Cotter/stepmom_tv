from flask import Flask, jsonify, request, Response
import os
import paho.mqtt.client as mqtt
import threading
import time
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# CONFIG
VIDEO_DIR = "/media/usb"
MQTT_BROKER = "192.168.50.1"
MQTT_PORT = 1883
MQTT_TOPIC_PLAY = "video/play"
MQTT_TOPIC_HEARTBEAT = "clients/status"
MQTT_TOPIC_ACK = "video/ack"
MQTT_TOPIC_PAUSE = "video/pause"
MQTT_TOPIC_STOP = "video/stop"
HEARTBEAT_TIMEOUT = 10  # seconds
ACK_TIMEOUT = 5  # seconds to wait for acknowledgments
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 0.2  # seconds between retries

VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm', '.mpeg', '.mpg', '.ts')

class VideoControlSystem:
    def __init__(self):
        self.app = Flask(__name__)
        self.mqtt_client = mqtt.Client()
        self.video_files: List[str] = []
        self.clients_last_seen: Dict[str, float] = {}
        self.pending_commands: Dict[str, dict] = {}
        self.command_lock = threading.Lock()
        self.setup_routes()
        self.setup_mqtt()
        
    def setup_mqtt(self):
        """Configure MQTT client with proper error handling"""
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.on_disconnect = self.on_disconnect
        self.mqtt_client.on_publish = self.on_publish
        
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT Broker successfully")
            client.subscribe([(MQTT_TOPIC_HEARTBEAT, 1), (MQTT_TOPIC_ACK, 1)])
        else:
            logger.error(f"Failed to connect to MQTT Broker, return code {rc}")
    
    def on_disconnect(self, client, userdata, rc):
        logger.warning(f"Disconnected from MQTT Broker, return code {rc}")
        
    def on_publish(self, client, userdata, mid):
        logger.debug(f"Message published with mid: {mid}")

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            logger.debug(f"Received message on {topic}: {payload}")
            
            if topic == MQTT_TOPIC_HEARTBEAT:
                self.handle_heartbeat(payload)
            elif topic == MQTT_TOPIC_ACK:
                self.handle_acknowledgment(payload)
                
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
    
    def handle_heartbeat(self, client_id: str):
        """Process client heartbeat messages"""
        self.clients_last_seen[client_id] = time.time()
        logger.debug(f"Heartbeat received from client: {client_id}")
    
    def handle_acknowledgment(self, payload: str):
        """Process acknowledgment messages from clients"""
        try:
            parts = payload.split(":")
            if len(parts) >= 3:
                client_id, command_id, status = parts[0], parts[1], parts[2]
                
                with self.command_lock:
                    if command_id in self.pending_commands:
                        if "acks" not in self.pending_commands[command_id]:
                            self.pending_commands[command_id]["acks"] = {}
                        
                        self.pending_commands[command_id]["acks"][client_id] = {
                            "status": status,
                            "timestamp": time.time()
                        }
                        logger.info(f"ACK received from {client_id} for command {command_id}: {status}")
                        
        except Exception as e:
            logger.error(f"Error parsing ACK message '{payload}': {e}")

    def update_video_list(self):
        """Scan directory and update available video files"""
        try:
            if os.path.exists(VIDEO_DIR):
                self.video_files = sorted([
                    f for f in os.listdir(VIDEO_DIR) 
                    if f.lower().endswith(VIDEO_EXTENSIONS)
                ])
                logger.info(f"Found {len(self.video_files)} video files")
            else:
                logger.warning(f"Video directory {VIDEO_DIR} does not exist")
                self.video_files = []
        except Exception as e:
            logger.error(f"Error updating video list: {e}")
            self.video_files = []

    def cleanup_inactive_clients(self):
        """Remove clients that haven't sent heartbeat recently"""
        while True:
            try:
                now = time.time()
                inactive_clients = [
                    client_id for client_id, last_seen in self.clients_last_seen.items()
                    if now - last_seen > HEARTBEAT_TIMEOUT
                ]
                
                for client_id in inactive_clients:
                    logger.info(f"Removing inactive client: {client_id}")
                    del self.clients_last_seen[client_id]
                    
                time.sleep(HEARTBEAT_TIMEOUT)
            except Exception as e:
                logger.error(f"Error in client cleanup: {e}")
                time.sleep(5)

    def cleanup_old_commands(self):
        """Remove old pending commands to prevent memory leaks"""
        while True:
            try:
                now = time.time()
                with self.command_lock:
                    expired_commands = [
                        cmd_id for cmd_id, cmd_data in self.pending_commands.items()
                        if now - cmd_data["timestamp"] > ACK_TIMEOUT * 2
                    ]
                    
                    for cmd_id in expired_commands:
                        logger.info(f"Cleaning up expired command: {cmd_id}")
                        del self.pending_commands[cmd_id]
                        
                time.sleep(ACK_TIMEOUT)
            except Exception as e:
                logger.error(f"Error in command cleanup: {e}")
                time.sleep(5)

    def publish_with_retry(self, topic: str, message: str, qos: int = 1, retain: bool = False) -> bool:
        """Publish MQTT message with retry logic"""
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                result = self.mqtt_client.publish(topic, message, qos=qos, retain=retain)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    logger.debug(f"MQTT publish successful (attempt {attempt + 1})")
                    return True
                else:
                    logger.warning(f"MQTT publish failed (attempt {attempt + 1}): rc={result.rc}")
            except Exception as e:
                logger.error(f"MQTT publish exception (attempt {attempt + 1}): {e}")
            
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                time.sleep(RETRY_DELAY)
        
        logger.error(f"Failed to publish to {topic} after {MAX_RETRY_ATTEMPTS} attempts")
        return False

    def send_video_command(self, video_index: int, delay: float = 4.0) -> Optional[str]:
        """Send video play command to all clients"""
        if not (0 <= video_index < len(self.video_files)):
            return None
            
        command_id = str(uuid.uuid4())
        start_time = time.time() + delay
        
        # Store command for tracking
        with self.command_lock:
            self.pending_commands[command_id] = {
                "video_index": video_index,
                "start_time": start_time,
                "timestamp": time.time(),
                "expected_clients": len(self.clients_last_seen),
                "acks": {}
            }
        
        # Prepare message
        message = f"{video_index},{start_time},{command_id}"
        logger.info(f"Sending video command: {message}")
        
        # Send with retry logic
        success = self.publish_with_retry(MQTT_TOPIC_PLAY, message, qos=1)
        
        if success:
            # Also send with retain flag for late-joining clients
            self.publish_with_retry(MQTT_TOPIC_PLAY, message, qos=1, retain=True)
            
            # Clear retained message after delay
            def clear_retained():
                time.sleep(2.0)
                self.publish_with_retry(MQTT_TOPIC_PLAY, "", retain=True)
            
            threading.Thread(target=clear_retained, daemon=True).start()
            return command_id
        
        return None

    def get_command_status(self, command_id: str) -> Optional[dict]:
        """Get status of a pending command"""
        with self.command_lock:
            if command_id not in self.pending_commands:
                return None
                
            cmd_data = self.pending_commands[command_id]
            acks = cmd_data.get("acks", {})
            
            success_count = sum(1 for ack in acks.values() if ack["status"] == "success")
            error_count = sum(1 for ack in acks.values() if ack["status"] == "error")
            total_responses = len(acks)
            expected_clients = cmd_data["expected_clients"]
            time_elapsed = time.time() - cmd_data["timestamp"]
            
            completed = (total_responses >= expected_clients) or (time_elapsed > ACK_TIMEOUT)
            
            return {
                "completed": completed,
                "success_count": success_count,
                "error_count": error_count,
                "total_responses": total_responses,
                "expected_clients": expected_clients,
                "time_elapsed": time_elapsed
            }

    def setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route("/")
        def index():
            self.update_video_list()
            buttons_html = "\n".join(
                f'<button class="video-btn" data-index="{i}">{v}</button>'
                for i, v in enumerate(self.video_files)
            )
            
            # Enhanced HTML with better error handling and accessibility
            html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Stepmom TV Control</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Baloo+2:wght@400;600&display=swap');
  
  * {{
    box-sizing: border-box;
  }}
  
  body {{
    background: linear-gradient(135deg, #ffeaa7, #fd79a8);
    font-family: 'Baloo 2', cursive;
    text-align: center;
    padding: 20px;
    min-height: 100vh;
    margin: 0;
  }}
  
  .container {{
    max-width: 800px;
    margin: 0 auto;
    background: rgba(255, 255, 255, 0.1);
    backdrop-filter: blur(10px);
    border-radius: 20px;
    padding: 30px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  }}
  
  h1 {{
    font-size: 3em;
    margin-bottom: 0.5em;
    color: #2d3436;
    font-weight: 600;
    text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.1);
  }}
  
  .client-info {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: rgba(255, 255, 255, 0.2);
    padding: 15px;
    border-radius: 15px;
    margin-bottom: 20px;
    font-size: 1.1em;
    color: #2d3436;
  }}
  
  .video-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 15px;
    margin: 20px 0;
  }}
  
  .video-btn {{
    background: linear-gradient(135deg, #6c5ce7, #a29bfe);
    border: none;
    border-radius: 15px;
    color: white;
    font-size: 1.1em;
    font-weight: 600;
    padding: 20px 15px;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(108, 92, 231, 0.3);
    word-break: break-word;
  }}
  
  .video-btn:hover:not(:disabled) {{
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(108, 92, 231, 0.4);
  }}
  
  .video-btn:active {{
    transform: translateY(0);
  }}
  
  .video-btn:disabled {{
    background: #95a5a6;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }}
  
  .status-message {{
    font-size: 1.1em;
    margin: 15px 0;
    padding: 15px;
    border-radius: 15px;
    display: none;
    font-weight: 600;
  }}
  
  .status-success {{
    background: linear-gradient(135deg, #00b894, #55efc4);
    color: white;
  }}
  
  .status-error {{
    background: linear-gradient(135deg, #e17055, #fab1a0);
    color: white;
  }}
  
  .status-warning {{
    background: linear-gradient(135deg, #fdcb6e, #f39c12);
    color: white;
  }}
  
  .loading {{
    display: inline-block;
    width: 20px;
    height: 20px;
    border: 3px solid rgba(255,255,255,.3);
    border-radius: 50%;
    border-top-color: #fff;
    animation: spin 1s ease-in-out infinite;
    margin-left: 10px;
  }}
  
  @keyframes spin {{
    to {{ transform: rotate(360deg); }}
  }}
  
  @media (max-width: 600px) {{
    .container {{
      margin: 10px;
      padding: 20px;
    }}
    
    h1 {{
      font-size: 2em;
    }}
    
    .client-info {{
      flex-direction: column;
      gap: 10px;
    }}
    
    .video-grid {{
      grid-template-columns: 1fr;
    }}
  }}
</style>
</head>
<body>
  <div class="container">
    <h1>🎬 Stepmom TV Control</h1>
    
    <div class="client-info">
      <div>📱 Connected Clients: <span id="clientCount">0</span></div>
      <div>🎥 Available Videos: {len(self.video_files)}</div>
    </div>
    
    <div id="status-message" class="status-message"></div>
    
    <div class="video-grid" id="buttons-container">
      {buttons_html}
    </div>
  </div>

  <canvas id="confetti-canvas" style="position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:1000;"></canvas>

<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
<script>
  const buttons = document.querySelectorAll('.video-btn');
  const clientCountSpan = document.getElementById('clientCount');
  const statusMessage = document.getElementById('status-message');
  let lastClickTime = 0;
  let isProcessing = false;

  function showStatus(message, type, showLoading = false) {{
    statusMessage.innerHTML = message + (showLoading ? '<span class="loading"></span>' : '');
    statusMessage.className = `status-message status-${{type}}`;
    statusMessage.style.display = 'block';
    
    if (!showLoading) {{
      setTimeout(() => {{
        statusMessage.style.display = 'none';
      }}, 5000);
    }}
  }}

  function disableButtons() {{
    buttons.forEach(btn => btn.disabled = true);
    isProcessing = true;
  }}

  function enableButtons() {{
    buttons.forEach(btn => btn.disabled = false);
    isProcessing = false;
  }}

  buttons.forEach(btn => {{
    btn.addEventListener('click', () => {{
      if (isProcessing) return;
      
      const now = Date.now();
      if (now - lastClickTime < 3000) {{
        const remaining = Math.ceil((3000 - (now - lastClickTime)) / 1000);
        showStatus(`⏳ Please wait ${{remaining}} more second(s)`, 'warning');
        return;
      }}
      
      lastClickTime = now;
      const index = btn.getAttribute('data-index');
      const videoName = btn.textContent;
      
      disableButtons();
      showStatus(`🚀 Starting ${{videoName}}...`, 'warning', true);

      fetch('/api/play', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ index: parseInt(index) }})
      }})
      .then(resp => resp.json())
      .then(data => {{
        if(data.status === 'success') {{
          checkCommandStatus(data.command_id, videoName);
        }} else {{
          showStatus(`❌ Error: ${{data.message}}`, 'error');
          enableButtons();
        }}
      }})
      .catch(err => {{
        showStatus(`🔌 Network error: ${{err.message}}`, 'error');
        enableButtons();
      }});
    }});
  }});

  function checkCommandStatus(commandId, videoName) {{
    let attempts = 0;
    const maxAttempts = 15;
    
    const checkInterval = setInterval(() => {{
      attempts++;
      
      fetch(`/api/command/status/${{commandId}}`)
        .then(resp => resp.json())
        .then(data => {{
          if (!data.completed) {{
            const elapsed = Math.floor(data.time_elapsed);
            const responses = data.total_responses;
            const expected = data.expected_clients;
            showStatus(`📊 ${{videoName}}: ${{responses}}/${{expected}} responses (${{elapsed}}s)`, 'warning', true);
          }}
          
          if (data.completed) {{
            clearInterval(checkInterval);
            enableButtons();
            
            if (data.success_count > 0) {{
              const successMsg = data.error_count > 0 
                ? `⚠️ ${{videoName}} started on ${{data.success_count}} client(s), ${{data.error_count}} failed`
                : `✅ ${{videoName}} started successfully on ${{data.success_count}} client(s)!`;
              
              showStatus(successMsg, data.error_count > 0 ? 'warning' : 'success');
              
              if (data.error_count === 0) {{
                confetti({{
                  particleCount: 100,
                  spread: 70,
                  origin: {{ y: 0.6 }},
                  colors: ['#6c5ce7', '#a29bfe', '#fd79a8', '#ffeaa7']
                }});
              }}
            }} else if (data.total_responses === 0) {{
              showStatus(`📵 No clients responded - check connections`, 'error');
            }} else {{
              showStatus(`❌ All clients failed to start ${{videoName}}`, 'error');
            }}
          }} else if (attempts >= maxAttempts) {{
            clearInterval(checkInterval);
            enableButtons();
            showStatus(`⏰ Timeout waiting for ${{videoName}} responses`, 'error');
          }}
        }})
        .catch(err => {{
          if (attempts >= maxAttempts) {{
            clearInterval(checkInterval);
            enableButtons();
            showStatus('❌ Status check failed', 'error');
          }}
        }});
    }}, 1000);
  }}

  function updateClientCount() {{
    fetch('/api/clients/count')
      .then(response => response.json())
      .then(data => {{
        clientCountSpan.textContent = data.count;
      }})
      .catch(() => {{
        clientCountSpan.textContent = '?';
      }});
  }}

  // Initial update and periodic refresh
  updateClientCount();
  setInterval(updateClientCount, 3000);
</script>
</body>
</html>
"""
            return Response(html, mimetype="text/html")

        @self.app.route("/api/play", methods=["POST"])
        def api_play():
            try:
                data = request.json
                video_index = data.get("index")
                
                if video_index is None or not (0 <= video_index < len(self.video_files)):
                    return jsonify({"status": "error", "message": "Invalid video index"}), 400
                
                if not self.clients_last_seen:
                    return jsonify({"status": "error", "message": "No clients connected"}), 400
                
                command_id = self.send_video_command(video_index)
                
                if command_id:
                    return jsonify({"status": "success", "command_id": command_id})
                else:
                    return jsonify({"status": "error", "message": "Failed to send command"}), 500
                    
            except Exception as e:
                logger.error(f"Error in play endpoint: {e}")
                return jsonify({"status": "error", "message": "Internal server error"}), 500

        @self.app.route("/api/command/status/<command_id>")
        def api_command_status(command_id):
            try:
                status = self.get_command_status(command_id)
                if status is None:
                    return jsonify({"error": "Command not found"}), 404
                return jsonify(status)
            except Exception as e:
                logger.error(f"Error getting command status: {e}")
                return jsonify({"error": "Internal server error"}), 500

        @self.app.route("/api/clients/count")
        def api_clients_count():
            return jsonify({"count": len(self.clients_last_seen)})

        @self.app.route("/api/debug/commands")
        def api_debug_commands():
            """Debug endpoint for monitoring commands"""
            with self.command_lock:
                return jsonify({
                    "pending_commands": self.pending_commands,
                    "total_commands": len(self.pending_commands)
                })

        @self.app.route("/api/health")
        def api_health():
            """Health check endpoint"""
            return jsonify({
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "mqtt_connected": self.mqtt_client.is_connected(),
                "video_count": len(self.video_files),
                "client_count": len(self.clients_last_seen)
            })

    def start_background_tasks(self):
        """Start background monitoring tasks"""
        
        # Client cleanup task
        cleanup_thread = threading.Thread(target=self.cleanup_inactive_clients, daemon=True)
        cleanup_thread.start()
        
        # Command cleanup task
        command_cleanup_thread = threading.Thread(target=self.cleanup_old_commands, daemon=True)
        command_cleanup_thread.start()
        
        logger.info("Background tasks started")

    def connect_mqtt(self):
        """Connect to MQTT broker with retry logic"""
        max_retries = 5
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT} (attempt {attempt + 1})")
                self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
                
                # Start MQTT loop in background
                mqtt_thread = threading.Thread(target=self.mqtt_client.loop_forever, daemon=True)
                mqtt_thread.start()
                
                logger.info("MQTT connection established")
                return True
                
            except Exception as e:
                logger.error(f"MQTT connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
        
        logger.error("Failed to connect to MQTT broker after multiple attempts")
        return False

    def run(self, host="0.0.0.0", port=5000, debug=False):
        """Start the application"""
        logger.info("Starting Video Control System")
        
        # Initialize video list
        self.update_video_list()
        
        # Connect to MQTT
        if not self.connect_mqtt():
            logger.error("Cannot start without MQTT connection")
            return
        
        # Start background tasks
        self.start_background_tasks()
        
        # Start Flask app
        logger.info(f"Starting web server on {host}:{port}")
        self.app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    system = VideoControlSystem()
    system.run()