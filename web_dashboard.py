"""
Starts your existing multi_udp_server threads,
then launches a Flask-SocketIO app that streams the same data
to a web page.
"""


# --- web_dashboard.py (very top, before any other import) ------------
import eventlet
eventlet.monkey_patch()        # <-- PATCHES socket, threading, time, etc.

import threading
import queue
from pathlib import Path
from datetime import datetime

import yaml
from flask import request, jsonify

# ---- import your original python server as a module -----------
import multi_udp_server                        # noqa: F401
from multi_udp_server import latest, feed_50050   # <-- add these exports

# ---- Flask web layer ------------------------------------------
from flask import Flask, render_template
from flask_socketio import SocketIO

from pathlib import Path
ROOT = Path(__file__).resolve().parent          # folder where the .py lives
app  = Flask(__name__, template_folder=ROOT / "templates")

LOG_FILE = Path(__file__).with_name("udp_log.txt")
HTTP_PORT = 8080

# app = Flask(__name__, template_folder="templates")
socketio = SocketIO(app, cors_allowed_origins="*")

# push queue (threads → websocket)
q: "queue.Queue[tuple[int,str]]" = queue.Queue()

# --- small helper the UDP threads can call ---------------------
def publish(port: int, msg: str):
    """Called by multi_udp_server when a UDP frame arrives."""
    q.put((port, msg))
    # optionally log
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as fp:
        fp.write(f"[{ts}] [PORT {port}] {msg}\n")

# monkey-patch the callback into your server
multi_udp_server.PUBLISH_FN = publish      # <- add this variable in your code

# background task: drain queue → socket.io
def pump():
    while True:
        port, msg = q.get()
        if port == 50050:
            socketio.emit("feed", {"msg": msg})
        else:
            socketio.emit("latest", {"port": port, "msg": msg})

socketio.start_background_task(pump)

@app.route("/")
def index():
    return render_template("index.html")

DEVFILE = Path(__file__).with_name("devices.yaml")

@app.route("/api/devices", methods=["GET"])
def get_devices():
    if not DEVFILE.exists():
        DEVFILE.write_text("# empty\n", encoding="utf-8")
    return jsonify({"text": DEVFILE.read_text(encoding="utf-8")})

@app.route("/api/devices", methods=["POST"])
def save_devices():
    data = request.get_json(force=True)
    text = data.get("text", "")
    # simple sanity-check: is it valid YAML?
    try:
        yaml.safe_load(text or "{}")
    except yaml.YAMLError as e:
        return jsonify({"status": "error", "msg": str(e)}), 400
    DEVFILE.write_text(text, encoding="utf-8")
    return jsonify({"status": "ok"})

# add near the other routes in web_dashboard.py
@app.route("/ping")
def ping():
    return "pong"


if __name__ == "__main__":
    multi_udp_server.start()            # ← call your new helper
    print(f"🌐  dashboard: http://localhost:{HTTP_PORT}")
    socketio.run(app, host="0.0.0.0", port=HTTP_PORT)
