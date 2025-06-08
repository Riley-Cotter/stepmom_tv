import time
import threading
import json
from flask import Flask, jsonify
import paho.mqtt.client as mqtt

# MQTT config
MQTT_BROKER = "192.168.50.1"
MQTT_PORT = 1883
MQTT_TOPIC_CLIENT_JOIN = "video/list"
MQTT_TOPIC_REQUEST_PLAY = "video/request_play"
MQTT_TOPIC_PLAY = "video/play"
MQTT_TOPIC_TIME_REQUEST = "sync/time/request"
MQTT_TOPIC_TIME_RESPONSE = "sync/time"

# Track connected clients
connected_clients = set()

# Flask app
app = Flask(__name__)

@app.route('/clients')
def get_clients():
    # Return sorted client list as JSON
    return jsonify(sorted(list(connected_clients)))


def run_flask():
    # Run Flask in a background thread
    app.run(host='0.0.0.0', port=5000)


def add_client(client_id):
    if client_id not in connected_clients:
        print(f"[Brain] New client connected: {client_id}")
    connected_clients.add(client_id)


# MQTT callbacks
def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected with result code {rc}")
    client.subscribe(MQTT_TOPIC_CLIENT_JOIN)
    client.subscribe(MQTT_TOPIC_REQUEST_PLAY)
    client.subscribe(MQTT_TOPIC_TIME_REQUEST)


def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    if topic == MQTT_TOPIC_CLIENT_JOIN:
        client_id = payload
        add_client(client_id)
        sync_idle_loop()
    elif topic == MQTT_TOPIC_REQUEST_PLAY:
        try:
            index_str, delay_str = payload.split(',')
            index = int(index_str.strip())
            delay = float(delay_str.strip())
            print(f"[Brain] Play request received: index={index}, delay={delay}s")
            schedule_video(index, delay)
        except Exception as e:
            print(f"[Brain] Invalid play request payload: {e}")
    elif topic == MQTT_TOPIC_TIME_REQUEST:
        now = time.time()
        print(f"[Sync] Time sync request received, sending {now}")
        client.publish(MQTT_TOPIC_TIME_RESPONSE, str(now))


def connect_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    return client


def schedule_video(index, delay_seconds):
    target_time = time.time() + delay_seconds
    payload = f"{index},{target_time}"
    client.publish(MQTT_TOPIC_PLAY, payload)
    print(f"[Brain] Scheduled video {index} to play in {delay_seconds:.2f}s (at {target_time})")


def sync_idle_loop():
    target_time = time.time() + 2
    payload = f"0,{target_time}"
    client.publish(MQTT_TOPIC_PLAY, payload)
    print(f"[Brain] Sent idle loop sync for time {target_time}")


if __name__ == "__main__":
    # Start Flask server thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    client = connect_mqtt()

    print("[Brain] Running... Waiting for MQTT messages and serving client list on http://0.0.0.0:5000/clients")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Brain] Shutting down...")
        client.loop_stop()
