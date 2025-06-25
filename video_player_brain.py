from flask import Flask, jsonify, request, Response
import os
import paho.mqtt.client as mqtt
import threading
import time
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# CONFIG - Keeping original values for compatibility
VIDEO_DIR = "/media/usb"
MQTT_BROKER = "192.168.50.1"
MQTT_TOPIC_PLAY = "video/play"
MQTT_TOPIC_HEARTBEAT = "clients/status"
MQTT_TOPIC_ACK = "video/ack"
HEARTBEAT_TIMEOUT = 10  # seconds
ACK_TIMEOUT = 5  # seconds to wait for acknowledgments

VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm', '.mpeg', '.mpg', '.ts')

app = Flask(__name__)
mqtt_client = mqtt.Client()

video_files = []
clients_last_seen = {}
pending_commands = {}  # Track commands waiting for acknowledgment
command_lock = threading.Lock()

def update_video_list():
    global video_files
    try:
        if os.path.exists(VIDEO_DIR):
            video_files = sorted(
                [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(VIDEO_EXTENSIONS)]
            )
            logger.info(f"Found {len(video_files)} videos: {video_files[:3]}{'...' if len(video_files) > 3 else ''}")
        else:
            logger.warning(f"Video directory {VIDEO_DIR} does not exist")
            video_files = []
    except Exception as e:
        logger.error(f"Error updating video list: {e}")
        video_files = []

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("✅ Connected to MQTT Broker successfully")
        client.subscribe(MQTT_TOPIC_HEARTBEAT)
        client.subscribe(MQTT_TOPIC_ACK)
    else:
        logger.error(f"❌ Failed to connect to MQTT Broker, return code {rc}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        logger.warning(f"🔌 Unexpected MQTT disconnection, return code {rc}")

def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        # Safely decode payload with error handling
        try:
            payload = msg.payload.decode('utf-8')
        except UnicodeDecodeError:
            logger.warning(f"⚠️ Failed to decode message from {topic}, skipping")
            return
            
        logger.debug(f"📨 Received: {topic} -> {payload}")
        
        if topic == MQTT_TOPIC_HEARTBEAT:
            # Handle heartbeat - keep original simple format
            client_id = payload.strip()
            if client_id:  # Only process non-empty client IDs
                clients_last_seen[client_id] = time.time()
                logger.debug(f"💓 Heartbeat from: {client_id}")
        
        elif topic == MQTT_TOPIC_ACK:
            # Handle acknowledgment: format is "client_id:command_id:status"
            try:
                parts = payload.split(":")
                if len(parts) >= 3:
                    client_id = parts[0].strip()
                    command_id = parts[1].strip()  
                    status = parts[2].strip()
                    
                    with command_lock:
                        if command_id in pending_commands:
                            if "acks" not in pending_commands[command_id]:
                                pending_commands[command_id]["acks"] = {}
                            pending_commands[command_id]["acks"][client_id] = {
                                "status": status,
                                "timestamp": time.time()
                            }
                            logger.info(f"✅ ACK from {client_id} for {command_id}: {status}")
                        else:
                            logger.debug(f"🤷 ACK for unknown command: {command_id}")
                else:
                    logger.warning(f"⚠️ Invalid ACK format: {payload}")
            except Exception as e:
                logger.error(f"❌ Error parsing ACK '{payload}': {e}")
                
    except Exception as e:
        logger.error(f"❌ Error in on_message: {e}")

def cleanup_clients():
    """Remove inactive clients - with better error handling"""
    while True:
        try:
            now = time.time()
            to_remove = []
            for cid, last in clients_last_seen.items():
                if now - last > HEARTBEAT_TIMEOUT:
                    logger.info(f"🗑️ Removing inactive client: {cid}")
                    to_remove.append(cid)
            
            for cid in to_remove:
                del clients_last_seen[cid]
                
            time.sleep(HEARTBEAT_TIMEOUT // 2)  # Check more frequently
        except Exception as e:
            logger.error(f"❌ Error in cleanup_clients: {e}")
            time.sleep(5)

def cleanup_old_commands():
    """Clean up old pending commands - with better error handling"""
    while True:
        try:
            now = time.time()
            with command_lock:
                to_remove = []
                for cmd_id, cmd_data in pending_commands.items():
                    if now - cmd_data["timestamp"] > ACK_TIMEOUT * 3:  # Give more time
                        to_remove.append(cmd_id)
                
                for cmd_id in to_remove:
                    logger.debug(f"🧹 Cleaning up old command: {cmd_id}")
                    del pending_commands[cmd_id]
                    
            time.sleep(ACK_TIMEOUT)
        except Exception as e:
            logger.error(f"❌ Error in cleanup_old_commands: {e}")
            time.sleep(5)

@app.route("/")
def index():
    update_video_list()
    buttons_html = "\n".join(
        f'<button class="video-btn" data-index="{i}">{v}</button>'
        for i, v in enumerate(video_files)
    )
    
    # Keep the original HTML structure but with minor improvements
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Stepmom TV</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Baloo+2&display=swap');
  body {{
    background-color: lightpink;
    font-family: 'Baloo 2', cursive;
    text-align: center;
    padding: 20px;
  }}
  h1 {{
    font-size: 3em;
    margin-bottom: 0.5em;
    color: #d147a3;
  }}
  .client-count {{
    font-size: 1.2em;
    margin-bottom: 1em;
    color: #7a1e63;
    background: rgba(255,255,255,0.3);
    padding: 10px;
    border-radius: 10px;
    display: inline-block;
  }}
  .video-btn {{
    background-color: #ff6f91;
    border: none;
    border-radius: 15px;
    color: white;
    font-size: 1.3em;
    padding: 15px 30px;
    margin: 10px;
    cursor: pointer;
    transition: background-color 0.3s;
  }}
  .video-btn:hover {{
    background-color: #ff4a75;
  }}
  .video-btn:disabled {{
    background-color: #cccccc;
    cursor: not-allowed;
  }}
  .status-message {{
    font-size: 1.1em;
    margin: 10px;
    padding: 10px;
    border-radius: 10px;
    display: none;
  }}
  .status-success {{
    background-color: #d4edda;
    color: #155724;
  }}
  .status-error {{
    background-color: #f8d7da;
    color: #721c24;
  }}
  .status-warning {{
    background-color: #fff3cd;
    color: #856404;
  }}
  .debug-info {{
    position: fixed;
    top: 10px;
    right: 10px;
    background: rgba(0,0,0,0.8);
    color: white;
    padding: 5px 10px;
    border-radius: 5px;
    font-size: 0.8em;
    font-family: monospace;
  }}
</style>
</head>
<body>
  <h1>Stepmom TV</h1>
  
  <!-- Debug info for troubleshooting -->
  <div class="debug-info" id="debug-info">
    Status: Loading...
  </div>
  
  <div class="client-count">
    Connected Clients: <span id="clientCount">0</span> | 
    Videos Available: {len(video_files)}
  </div>
  
  <div id="status-message" class="status-message"></div>
  <div id="buttons-container">{buttons_html}</div>

  <canvas id="confetti-canvas" style="position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;"></canvas>

<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
<script>
  const buttons = document.querySelectorAll('.video-btn');
  const clientCountSpan = document.getElementById('clientCount');
  const statusMessage = document.getElementById('status-message');
  const debugInfo = document.getElementById('debug-info');
  let lastClickTime = 0;

  function updateDebugInfo(info) {{
    debugInfo.textContent = `${{new Date().toLocaleTimeString()}} - ${{info}}`;
  }}

  function showStatus(message, type) {{
    statusMessage.textContent = message;
    statusMessage.className = `status-message status-${{type}}`;
    statusMessage.style.display = 'block';
    updateDebugInfo(`Status: ${{type}} - ${{message}}`);
    
    setTimeout(() => {{
      statusMessage.style.display = 'none';
    }}, 5000);
  }}

  function disableButtons() {{
    buttons.forEach(btn => btn.disabled = true);
  }}

  function enableButtons() {{
    buttons.forEach(btn => btn.disabled = false);
  }}

  buttons.forEach(btn => {{
    btn.addEventListener('click', () => {{
      const now = Date.now();
      // Keep original 5-second debounce
      if (now - lastClickTime < 5000) {{
        const remaining = Math.ceil((5000 - (now - lastClickTime)) / 1000);
        showStatus(`Please wait ${{remaining}} more second(s) before selecting another video`, 'warning');
        return;
      }}
      lastClickTime = now;

      const index = btn.getAttribute('data-index');
      const videoName = btn.textContent;
      
      updateDebugInfo(`Sending: ${{videoName}}`);
      disableButtons();
      showStatus(`Starting ${{videoName}}... sending command to clients`, 'warning');

      fetch('/play', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ index: parseInt(index) }})
      }})
      .then(resp => {{
        if (!resp.ok) {{
          throw new Error(`HTTP ${{resp.status}}`);
        }}
        return resp.json();
      }})
      .then(data => {{
        if(data.status === 'success') {{
          const commandId = data.command_id;
          updateDebugInfo(`Command sent: ${{commandId}}`);
          showStatus(`Command sent! Waiting for ${{videoName}} to start on clients...`, 'warning');
          checkCommandStatus(commandId, videoName);
        }} else {{
          updateDebugInfo(`Error: ${{data.message}}`);
          showStatus('Error: ' + data.message, 'error');
          enableButtons();
        }}
      }})
      .catch(err => {{
        updateDebugInfo(`Network error: ${{err.message}}`);
        showStatus('Network error: ' + err.message, 'error');
        enableButtons();
      }});
    }});
  }});

  function checkCommandStatus(commandId, videoName) {{
    let attempts = 0;
    const maxAttempts = 15;
    
    const checkInterval = setInterval(() => {{
      attempts++;
      
      fetch(`/command/status/${{commandId}}`)
        .then(resp => {{
          if (!resp.ok) throw new Error(`HTTP ${{resp.status}}`);
          return resp.json();
        }})
        .then(data => {{
          updateDebugInfo(`Check ${{attempts}}: ${{data.total_responses}}/${{data.expected_clients}} responses`);
          
          if (!data.completed) {{
            const elapsed = Math.floor(data.time_elapsed);
            const responses = data.total_responses;
            const expected = data.expected_clients;
            showStatus(`${{videoName}}: Got ${{responses}}/${{expected}} responses (${{elapsed}}s)`, 'warning');
          }}
          
          if (data.completed) {{
            clearInterval(checkInterval);
            enableButtons();
            
            if (data.success_count > 0) {{
              const successMsg = data.error_count > 0 
                ? `${{videoName}} started on ${{data.success_count}} client(s), ${{data.error_count}} failed`
                : `${{videoName}} started successfully on ${{data.success_count}} client(s)!`;
              
              showStatus(successMsg, data.error_count > 0 ? 'warning' : 'success');
              updateDebugInfo(`Complete: ${{data.success_count}} success, ${{data.error_count}} error`);
              
              if (data.error_count === 0) {{
                confetti({{
                  particleCount: 150,
                  spread: 60,
                  origin: {{ y: 0.6 }}
                }});
              }}
            }} else if (data.total_responses === 0) {{
              showStatus(`No clients responded to ${{videoName}} - check client connections`, 'error');
              updateDebugInfo('No client responses');
            }} else {{
              showStatus(`All clients failed to start ${{videoName}}`, 'error');
              updateDebugInfo('All clients failed');
            }}
          }} else if (attempts >= maxAttempts) {{
            clearInterval(checkInterval);
            enableButtons();
            updateDebugInfo('Timeout reached');
            
            if (data.total_responses > 0) {{
              showStatus(`${{videoName}}: Partial success - ${{data.success_count}} clients started`, 'warning');
            }} else {{
              showStatus(`Timeout waiting for clients to respond to ${{videoName}}`, 'error');
            }}
          }}
        }})
        .catch(err => {{
          console.error('Status check error:', err);
          updateDebugInfo(`Status error: ${{err.message}}`);
          if (attempts >= maxAttempts) {{
            clearInterval(checkInterval);
            enableButtons();
            showStatus('Error checking command status', 'error');
          }}
        }});
    }}, 1000);
  }}

  function updateClientCount() {{
    fetch('/clients/count')
      .then(response => {{
        if (!response.ok) throw new Error('Network error');
        return response.json();
      }})
      .then(data => {{
        clientCountSpan.textContent = data.count;
        updateDebugInfo(`Clients: ${{data.count}}`);
      }})
      .catch(err => {{
        clientCountSpan.textContent = '?';
        updateDebugInfo(`Client count error: ${{err.message}}`);
      }});
  }}

  // Initial setup
  updateDebugInfo('Initializing...');
  updateClientCount();
  setInterval(updateClientCount, 5000);
</script>
</body>
</html>
"""
    return Response(html, mimetype="text/html")

@app.route("/play", methods=["POST"])
def play():
    try:
        data = request.json
        video_index = data.get("index")
        
        if video_index is None or not (0 <= video_index < len(video_files)):
            logger.warning(f"⚠️ Invalid video index: {video_index}")
            return jsonify({"status": "error", "message": "Invalid video index"}), 400
        
        if not clients_last_seen:
            logger.warning("⚠️ No clients connected")
            return jsonify({"status": "error", "message": "No clients connected"}), 400
        
        # Use ORIGINAL timestamp-based command ID for compatibility
        command_id = f"{int(time.time())}{video_index}"
        start_time = time.time() + 4  # Keep original 4-second delay
        
        # Store command for tracking
        with command_lock:
            pending_commands[command_id] = {
                "video_index": video_index,
                "start_time": start_time,
                "timestamp": time.time(),
                "expected_clients": len(clients_last_seen),
                "acks": {}
            }
        
        # Use ORIGINAL message format that your clients expect
        message = f"{video_index},{start_time},{command_id}"
        logger.info(f"📤 Sending command: {message}")
        
        # Keep original retry logic but with better error handling
        success_count = 0
        for attempt in range(3):
            try:
                result = mqtt_client.publish(MQTT_TOPIC_PLAY, message, qos=1)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    logger.debug(f"✅ MQTT publish attempt {attempt + 1}/3: SUCCESS")
                    success_count += 1
                else:
                    logger.warning(f"⚠️ MQTT publish attempt {attempt + 1}/3: FAILED (rc={result.rc})")
            except Exception as e:
                logger.error(f"❌ MQTT publish attempt {attempt + 1}/3: EXCEPTION {e}")
            
            if attempt < 2:  # Small delay between retries
                time.sleep(0.2)
        
        # Also publish with retain flag (original behavior)
        try:
            mqtt_client.publish(MQTT_TOPIC_PLAY, message, qos=1, retain=True)
            logger.debug("📌 Published with retain flag")
            # Clear retained message after delay
            threading.Timer(2.0, lambda: mqtt_client.publish(MQTT_TOPIC_PLAY, "", retain=True)).start()
        except Exception as e:
            logger.error(f"❌ Failed to publish with retain: {e}")
        
        if success_count > 0:
            logger.info(f"✅ Command sent successfully ({success_count}/3 attempts)")
            return jsonify({"status": "success", "command_id": command_id})
        else:
            logger.error("❌ All MQTT publish attempts failed")
            return jsonify({"status": "error", "message": "Failed to send MQTT command"}), 500
            
    except Exception as e:
        logger.error(f"❌ Error in play endpoint: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500

@app.route("/command/status/<command_id>")
def command_status(command_id):
    try:
        with command_lock:
            if command_id not in pending_commands:
                logger.warning(f"⚠️ Command not found: {command_id}")
                return jsonify({"error": "Command not found"}), 404
            
            cmd_data = pending_commands[command_id]
            acks = cmd_data.get("acks", {})
            
            success_count = sum(1 for ack in acks.values() if ack["status"] == "success")
            error_count = sum(1 for ack in acks.values() if ack["status"] == "error")
            total_responses = len(acks)
            expected_clients = cmd_data["expected_clients"]
            
            time_elapsed = time.time() - cmd_data["timestamp"]
            completed = (total_responses >= expected_clients) or (time_elapsed > ACK_TIMEOUT)
            
            return jsonify({
                "completed": completed,
                "success_count": success_count,
                "error_count": error_count,
                "total_responses": total_responses,
                "expected_clients": expected_clients,
                "time_elapsed": time_elapsed
            })
    except Exception as e:
        logger.error(f"❌ Error getting command status: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/clients/count")
def clients_count():
    return jsonify({"count": len(clients_last_seen)})

@app.route("/debug/commands")
def debug_commands():
    """Debug endpoint to see pending commands"""
    try:
        with command_lock:
            return jsonify({
                "pending_commands": pending_commands,
                "total_commands": len(pending_commands),
                "active_clients": list(clients_last_seen.keys())
            })
    except Exception as e:
        logger.error(f"❌ Error in debug endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/health")
def health_check():
    """Simple health check"""
    return jsonify({
        "status": "healthy",
        "mqtt_connected": mqtt_client.is_connected(),
        "video_count": len(video_files),
        "client_count": len(clients_last_seen),
        "timestamp": time.time()
    })

if __name__ == "__main__":
    logger.info("🚀 Starting Stepmom TV Control System")
    
    # Initialize
    update_video_list()
    
    # Setup MQTT with better error handling
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.on_disconnect = on_disconnect
    
    try:
        logger.info(f"🔌 Connecting to MQTT broker at {MQTT_BROKER}:1883")
        mqtt_client.connect(MQTT_BROKER, 1883, 60)
        
        mqtt_thread = threading.Thread(target=mqtt_client.loop_forever, daemon=True)
        mqtt_thread.start()
        logger.info("✅ MQTT thread started")
        
    except Exception as e:
        logger.error(f"❌ Failed to connect to MQTT: {e}")
        exit(1)

    # Start background threads
    cleanup_thread = threading.Thread(target=cleanup_clients, daemon=True)
    cleanup_thread.start()
    logger.info("🧹 Client cleanup thread started")

    command_cleanup_thread = threading.Thread(target=cleanup_old_commands, daemon=True)
    command_cleanup_thread.start()
    logger.info("🗑️ Command cleanup thread started")

    logger.info("🌐 Starting Flask web server on 0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)