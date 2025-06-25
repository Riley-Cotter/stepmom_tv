from flask import Flask, jsonify, request, Response
import os
import paho.mqtt.client as mqtt
import threading
import time
import json

# CONFIG
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
    video_files = sorted(
        [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(VIDEO_EXTENSIONS)]
    )
    print(f"Found videos: {video_files}")

def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT Broker")
    client.subscribe(MQTT_TOPIC_HEARTBEAT)
    client.subscribe(MQTT_TOPIC_ACK)

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    
    if topic == MQTT_TOPIC_HEARTBEAT:
        # Handle heartbeat
        client_id = payload
        clients_last_seen[client_id] = time.time()
    
    elif topic == MQTT_TOPIC_ACK:
        # Handle acknowledgment: format is "client_id:command_id:status"
        try:
            parts = payload.split(":")
            if len(parts) >= 3:
                client_id = parts[0]
                command_id = parts[1]
                status = parts[2]
                
                with command_lock:
                    if command_id in pending_commands:
                        if "acks" not in pending_commands[command_id]:
                            pending_commands[command_id]["acks"] = {}
                        pending_commands[command_id]["acks"][client_id] = {
                            "status": status,
                            "timestamp": time.time()
                        }
                        print(f"Received ACK from {client_id} for command {command_id}: {status}")
        except Exception as e:
            print(f"Error parsing ACK message: {payload}, {e}")

def cleanup_clients():
    while True:
        now = time.time()
        to_remove = []
        for cid, last in clients_last_seen.items():
            if now - last > HEARTBEAT_TIMEOUT:
                print(f"Removing inactive client: {cid}")
                to_remove.append(cid)
        for cid in to_remove:
            del clients_last_seen[cid]
        time.sleep(HEARTBEAT_TIMEOUT)

def cleanup_old_commands():
    """Clean up old pending commands"""
    while True:
        now = time.time()
        with command_lock:
            to_remove = []
            for cmd_id, cmd_data in pending_commands.items():
                if now - cmd_data["timestamp"] > ACK_TIMEOUT * 2:
                    to_remove.append(cmd_id)
            for cmd_id in to_remove:
                print(f"Cleaning up old command: {cmd_id}")
                del pending_commands[cmd_id]
        time.sleep(ACK_TIMEOUT)

@app.route("/")
def index():
    update_video_list()
    buttons_html = "\n".join(
        f'<button class="video-btn" data-index="{i}">{v}</button>'
        for i, v in enumerate(video_files)
    )
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
</style>
</head>
<body>
  <h1>Stepmom TV</h1>
  <div class="client-count">Connected Clients: <span id="clientCount">0</span></div>
  <div id="status-message" class="status-message"></div>
  <div id="buttons-container">{buttons_html}</div>

  <canvas id="confetti-canvas" style="position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;"></canvas>

<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
<script>
  const buttons = document.querySelectorAll('.video-btn');
  const clientCountSpan = document.getElementById('clientCount');
  const statusMessage = document.getElementById('status-message');
  let lastClickTime = 0;

  function showStatus(message, type) {{
    statusMessage.textContent = message;
    statusMessage.className = `status-message status-${{type}}`;
    statusMessage.style.display = 'block';
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
      // ENHANCED BUTTON DEBOUNCING - 5 second cooldown
      if (now - lastClickTime < 5000) {{
        const remaining = Math.ceil((5000 - (now - lastClickTime)) / 1000);
        showStatus(`Please wait ${{remaining}} more second(s) before selecting another video`, 'warning');
        return;
      }}
      lastClickTime = now;

      const index = btn.getAttribute('data-index');
      const videoName = btn.textContent;
      
      // Disable all buttons immediately
      disableButtons();
      showStatus(`Starting ${{videoName}}... sending command to clients`, 'warning');

      fetch('/play', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ index: parseInt(index) }})
      }})
      .then(resp => resp.json())
      .then(data => {{
        if(data.status === 'success') {{
          const commandId = data.command_id;
          showStatus(`Command sent! Waiting for ${{videoName}} to start on clients...`, 'warning');
          checkCommandStatus(commandId, videoName);
        }} else {{
          showStatus('Error: ' + data.message, 'error');
          enableButtons();
        }}
      }})
      .catch(err => {{
        showStatus('Network error: ' + err.message, 'error');
        enableButtons();
      }});
    }});
  }});

  function checkCommandStatus(commandId, videoName) {{
    let attempts = 0;
    const maxAttempts = 15; // Check for 15 seconds (increased from 10)
    
    const checkInterval = setInterval(() => {{
      attempts++;
      
      fetch(`/command/status/${{commandId}}`)
        .then(resp => resp.json())
        .then(data => {{
          // Update status message with more detail
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
              
              // Only show confetti if at least one client succeeded
              confetti({{
                particleCount: 150,
                spread: 60,
                origin: {{ y: 0.6 }}
              }});
            }} else if (data.total_responses === 0) {{
              showStatus(`No clients responded to ${{videoName}} - check client connections`, 'error');
            }} else {{
              showStatus(`All clients failed to start ${{videoName}}`, 'error');
            }}
          }} else if (attempts >= maxAttempts) {{
            clearInterval(checkInterval);
            enableButtons();
            
            if (data.total_responses > 0) {{
              showStatus(`${{videoName}}: Partial success - ${{data.success_count}} clients started`, 'warning');
            }} else {{
              showStatus(`Timeout waiting for clients to respond to ${{videoName}}`, 'error');
            }}
          }}
        }})
        .catch(err => {{
          console.error('Status check error:', err);
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
      .then(response => response.json())
      .then(data => {{
        clientCountSpan.textContent = data.count;
      }});
  }}
  updateClientCount();
  setInterval(updateClientCount, 5000);
</script>
</body>
</html>
"""
    return Response(html, mimetype="text/html")

@app.route("/play", methods=["POST"])
def play():
    data = request.json
    video_index = data.get("index")
    if video_index is None or not (0 <= video_index < len(video_files)):
        return jsonify({"status": "error", "message": "Invalid video index"}), 400
    
    # Create unique command ID
    command_id = f"{int(time.time())}{video_index}"
    start_time = time.time() + 4  # 4 seconds delay for better preparation time
    
    # Store command for tracking
    with command_lock:
        pending_commands[command_id] = {
            "video_index": video_index,
            "start_time": start_time,
            "timestamp": time.time(),
            "expected_clients": len(clients_last_seen),
            "acks": {}
        }
    
    # RETRY LOGIC - Send command multiple times to ensure delivery
    message = f"{video_index},{start_time},{command_id}"
    
    print(f"Sending play command with retries: {message}")
    
    # Send message 3 times with slight delays to improve reliability
    for attempt in range(3):
        try:
            result = mqtt_client.publish(MQTT_TOPIC_PLAY, message, qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"MQTT publish attempt {attempt + 1}/3: SUCCESS")
            else:
                print(f"MQTT publish attempt {attempt + 1}/3: FAILED (rc={result.rc})")
        except Exception as e:
            print(f"MQTT publish attempt {attempt + 1}/3: EXCEPTION {e}")
        
        # Small delay between retries (except for last attempt)
        if attempt < 2:
            time.sleep(0.2)
    
    # Also publish with retain flag to help clients that might reconnect
    try:
        mqtt_client.publish(MQTT_TOPIC_PLAY, message, qos=1, retain=True)
        print("Published with retain flag")
        # Clear the retained message after a short delay
        threading.Timer(2.0, lambda: mqtt_client.publish(MQTT_TOPIC_PLAY, "", retain=True)).start()
    except Exception as e:
        print(f"Failed to publish with retain: {e}")
    
    return jsonify({"status": "success", "command_id": command_id})

@app.route("/command/status/<command_id>")
def command_status(command_id):
    with command_lock:
        if command_id not in pending_commands:
            return jsonify({"error": "Command not found"}), 404
        
        cmd_data = pending_commands[command_id]
        acks = cmd_data.get("acks", {})
        
        success_count = sum(1 for ack in acks.values() if ack["status"] == "success")
        error_count = sum(1 for ack in acks.values() if ack["status"] == "error")
        total_responses = len(acks)
        expected_clients = cmd_data["expected_clients"]
        
        # Consider command completed if we got responses from all expected clients
        # or if enough time has passed
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

@app.route("/clients/count")
def clients_count():
    return jsonify({"count": len(clients_last_seen)})

@app.route("/debug/commands")
def debug_commands():
    """Debug endpoint to see pending commands"""
    with command_lock:
        return jsonify({"pending_commands": pending_commands})

if __name__ == "__main__":
    update_video_list()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_BROKER, 1883, 60)

    mqtt_thread = threading.Thread(target=mqtt_client.loop_forever)
    mqtt_thread.daemon = True
    mqtt_thread.start()

    cleanup_thread = threading.Thread(target=cleanup_clients)
    cleanup_thread.daemon = True
    cleanup_thread.start()

    command_cleanup_thread = threading.Thread(target=cleanup_old_commands)
    command_cleanup_thread.daemon = True
    command_cleanup_thread.start()

    app.run(host="0.0.0.0", port=5000)