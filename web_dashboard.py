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

# ---------- Device inventory page --------------------------------------
@app.route("/devices")
def devices_page():
    """
    Show all units defined under the top-level `devices:` key of devices.yaml.
    Any other keys (e.g. `credentials:`) are ignored.
    Expected YAML:

        credentials:
          username: admin
          password: secret
        devices:
          living_room_light:
            ip: 192.168.1.50
            type: bulb
          bedroom_temp:
            ip: 192.168.1.60
            type: thermometer
    """
    if not DEVFILE.exists():
        devmap = {}
        error = None
    else:
        try:
            data = yaml.safe_load(DEVFILE.read_text(encoding="utf-8")) or {}
            devmap = data.get("devices", {}) or {}
            error = None
        except yaml.YAMLError as e:
            devmap = {}
            error = str(e)

    # devmap = {name: {ip: "...", type: "..."}}
    return render_template("devices.html", devices=devmap, error=error)

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

# ---------- helpers to manipulate devices.yaml -------------------------
def _load_devices_map() -> dict:
    """
    Return a normalized mapping:
        {name: {"ip": "...", "type": "..."}}

    • Accepts either mapping *or* list under the top-level `devices:` key.
    • Detects ip-keys named 'ip', 'ip_address', 'addr', 'address'.
    • Detects type-keys named 'type', 'device', 'device_type', 'kind'.
    """
    if not DEVFILE.exists():
        return {}

    try:
        data = yaml.safe_load(DEVFILE.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}

    raw = data.get("devices", {})
    devmap: dict = {}

    # helper to pull ip / type whatever the key spelling
    def normalize(item: dict, idx: int):
        name = (item.get("name")
                or item.get("device")
                or item.get("id")
                or f"device_{idx}")

        # find ip key
        ip = None
        for k in ("ip", "ip_address", "addr", "address"):
            if k in item:
                ip = item[k]
                break

        # find type key
        dtyp = None
        for k in ("type", "device", "device_type", "kind"):
            if k in item:
                dtyp = item[k]
                break

        devmap[name] = {"ip": ip, "type": dtyp}

    if isinstance(raw, dict):
        # {name:{ip:..., type:...}}
        for name, info in raw.items():
            if not isinstance(info, dict):
                info = {"ip": info}
            normalize({"name": name, **info}, 0)
    elif isinstance(raw, list):
        for idx, item in enumerate(raw, 1):
            if isinstance(item, dict):
                normalize(item, idx)

    return devmap

def _write_devices_map(devmap: dict):
    """Write the full YAML back, keeping any other top-level keys."""
    data = {}
    if DEVFILE.exists():
        try:
            data = yaml.safe_load(DEVFILE.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            pass
    data["devices"] = devmap
    DEVFILE.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
# -----------------------------------------------------------------------

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

# ---------- REST-ish endpoints used by the table JS --------------------
@app.route("/api/device", methods=["POST"])
def api_add_device():
    """
    JSON body: {name:"living_room", ip:"192.168.1.60", type:"bulb"}
    Adds or replaces that entry.
    """
    j = request.get_json(force=True)
    name, ip, dtyp = j.get("name"), j.get("ip"), j.get("type")
    if not (name and ip):
        return jsonify({"status": "error", "msg": "name and ip required"}), 400

    devmap = _load_devices_map()
    devmap[name] = {"ip": ip, "type": dtyp}
    _write_devices_map(devmap)
    return jsonify({"status": "ok"})

@app.route("/api/device/<name>", methods=["DELETE"])
def api_delete_device(name):
    devmap = _load_devices_map()
    if name not in devmap:
        return jsonify({"status": "error", "msg": "no such device"}), 404
    devmap.pop(name)
    _write_devices_map(devmap)
    return jsonify({"status": "ok"})
# -----------------------------------------------------------------------

# web_dashboard.py  (add near the other /api routes)
@app.route("/api/devices/list")
def api_list_devices():
    """Return just the parsed devices map: {name:{ip,type}, …}"""
    return jsonify(_load_devices_map())

# add near the other routes in web_dashboard.py
@app.route("/ping")
def ping():
    return "pong"


if __name__ == "__main__":
    multi_udp_server.start()            # ← call your new helper
    print(f"🌐  dashboard: http://localhost:{HTTP_PORT}")
    socketio.run(app, host="0.0.0.0", port=HTTP_PORT)
