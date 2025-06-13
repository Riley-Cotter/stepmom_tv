from flask import Flask, jsonify, request, Response
import os
import paho.mqtt.client as mqtt
import threading
import time

# CONFIG
VIDEO_DIR = "/media/usb"
MQTT_BROKER = "192.168.50.1"
MQTT_TOPIC_PLAY = "video/play"
MQTT_TOPIC_HEARTBEAT = "clients/status"
HEARTBEAT_TIMEOUT = 10  # seconds

VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm', '.mpeg', '.mpg', '.ts')

app = Flask(__name__)
mqtt_client = mqtt.Client()

video_files = []
clients_last_seen = {}

def update_video_list():
    global video_files
    video_files = sorted(
        [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(VIDEO_EXTENSIONS)]
    )
    print(f"Found videos: {video_files}")

def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT Broker")
    client.subscribe(MQTT_TOPIC_HEARTBEAT)

def on_message(client, userdata, msg):
    client_id = msg.payload.decode()
    clients_last_seen[client_id] = time.time()

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
</style>
</head>
<body>
  <h1>Stepmom TV</h1>
  <div class="client-count">Connected Clients: <span id="clientCount">0</span></div>
  <div id="buttons-container">{buttons_html}</div>

  <canvas id="confetti-canvas" style="position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;"></canvas>

<script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
<script>
  const buttons = document.querySelectorAll('.video-btn');
  const clientCountSpan = document.getElementById('clientCount');

  buttons.forEach(btn => {{
    btn.addEventListener('click', () => {{
      const index = btn.getAttribute('data-index');
      fetch('/play', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ index: parseInt(index) }})
      }}).then(resp => resp.json()).then(data => {{
        if(data.status === 'success') {{
          confetti({{
            particleCount: 150,
            spread: 60,
            origin: {{ y: 0.6 }}
          }});
        }} else {{
          alert('Error: ' + data.message);
        }}
      }});
    }});
  }});

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
    mqtt_client.publish(MQTT_TOPIC_PLAY, str(video_index))
    return jsonify({"status": "success"})

@app.route("/clients/count")
def clients_count():
    return jsonify({"count": len(clients_last_seen)})

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

    app.run(host="0.0.0.0", port=5000)
