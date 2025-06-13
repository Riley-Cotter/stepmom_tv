from flask import Flask, render_template, request, jsonify
import subprocess
import os

app = Flask(__name__, template_folder='/home/ri/stepmom_tv/')

MQTT_BROKER = "192.168.50.1"
MQTT_TOPIC_REQUEST = "video/request_play"  # Where web GUI publishes requests
MEDIA_PATH = "/media/usb/"

@app.route('/')
def index():
    video_files = [f for f in os.listdir(MEDIA_PATH) if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))]
    video_list = list(enumerate(video_files))
    return render_template('index.html', video_list=video_list)

@app.route('/play/<int:index>', methods=['POST'])
def play(index):
    # Send MQTT message to the brain to request playback of a video index
    command = [
        "mosquitto_pub", "-h", MQTT_BROKER,
        "-t", MQTT_TOPIC_REQUEST,
        "-m", f"{index},5"  # "5" is an example delay or start time offset (brain can interpret)
    ]
    try:
        subprocess.run(command, check=True)
        return jsonify({"status": "success", "index": index})
    except subprocess.CalledProcessError as e:
        return jsonify({"status": "failed", "error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
