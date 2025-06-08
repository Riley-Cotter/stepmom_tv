from flask import Flask, render_template
import subprocess
import os

app = Flask(__name__, template_folder='templates')

MQTT_BROKER = "192.168.50.1"
MQTT_TOPIC = "video/request_play"
MEDIA_PATH = "/media/usb/"

@app.route('/')
def index():
    video_files = [f for f in os.listdir(MEDIA_PATH) if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))]
    video_list = list(enumerate(video_files))
    return render_template('index.html', video_list=video_list)


@app.route('/play/<int:index>', methods=['POST'])
def play(index):
    command = [
        "mosquitto_pub", "-h", MQTT_BROKER,
        "-t", MQTT_TOPIC,
        "-m", f"{index},5"
    ]
    try:
        subprocess.run(command, check=True)
        return f"Sent index {index}"
    except subprocess.CalledProcessError as e:
        return f"Failed: {e}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
