import os
import sys
import socket
import asyncio
import threading
import ctypes
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from datetime import datetime

from tapo import ApiClient
from tapo.requests import Color
from tapo_manager import create_manager_from_config

# ======================== SETTINGS ========================
UDP_PORTS = [50000, 50001, 50002, 50050]
LOG_FILE = "udp_log.txt"
PORT_COLORS = {
    50000: "#005f87",  # Dark Blue
    50001: "#228B22",  # Forest Green
    50002: "#b36b00",  # Orange-Brown
}
console_visible = False
last_value_labels = {}
live_feed_box = None
log_lock = threading.Lock()

tapo_manager = None

# ======================== UTILITIES ========================

def hide_console():
    if os.name == 'nt':
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

def toggle_console(btn):
    global console_visible
    if os.name != 'nt':
        return

    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if console_visible:
        ctypes.windll.user32.ShowWindow(hwnd, 0)  # Hide
        btn.config(text="Show Console")
        console_visible = False
    else:
        ctypes.windll.user32.ShowWindow(hwnd, 1)  # Show
        btn.config(text="Hide Console")
        console_visible = True

def log_message(port, addr, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [PORT {port}] From {addr}: {message}\n"
    with log_lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)

def update_label(label, text):
    label.config(text=text)

def append_to_feed(text):
    live_feed_box.insert(tk.END, text)
    live_feed_box.see(tk.END)

# ======================== UDP LISTENER ========================

def udp_listener(port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", port))
        print(f"📡 Listening on UDP port {port}...")

        while True:
            try:
                data, addr = sock.recvfrom(1024)
                try:
                    message = data.decode("utf-8")
                except UnicodeDecodeError:
                    message = data.decode("utf-8", errors="replace")

                log_message(port, addr, message)

                if port == 50050:
                    if live_feed_box:
                        live_feed_box.after(0, append_to_feed, f"{message}\n")
                    try:
                        print(message)
                    except UnicodeEncodeError:
                        print("[Port 50050] Received message (emoji not printable)")
                else:
                    if port in last_value_labels:
                        last_value_labels[port].after(0, update_label, last_value_labels[port], message)

            except Exception as e:
                print(f"❌ Error receiving data on port {port}: {e}")
    except Exception as e:
        print(f"❌ Failed to bind port {port}: {e}")

# ======================== GUI ========================

def start_gui():
    global live_feed_box

    # Dark mode palette
    bg_color = "#1e1e1e"
    fg_color = "#ffffff"
    box_bg = "#2d2d2d"
    highlight_color = "#3e3e3e"

    root = tk.Tk()
    root.title("UDP Listener Dashboard")
    root.configure(bg=bg_color)

    # Latest values section
    info_frame = tk.LabelFrame(root, text="Latest Values from Ports 50000–50002", bg=bg_color, fg=fg_color, padx=10, pady=10)
    info_frame.pack(padx=10, pady=10, fill="x")

    emoji_map = {
        50000: "🌡️",  # Thermometer
        50001: "💡",  # Bulb
        50002: "💧",  # Humidity
    }

    for port in [50000, 50001, 50002]:
        row = tk.Frame(info_frame, bg=bg_color)
        row.pack(fill="x", pady=5)

        # Emoji icon
        icon_label = tk.Label(row, text=emoji_map.get(port, ""), font=("Segoe UI Emoji", 16), bg=bg_color, fg=fg_color)
        icon_label.pack(side="left", padx=5)

        # Port label
        label = tk.Label(row, text=f"Port {port}:", width=10, anchor='w', bg=bg_color, fg=fg_color)
        label.pack(side="left")

        # Value display
        value_label = tk.Label(
            row,
            text="(waiting...)",
            anchor='w',
            bg=PORT_COLORS.get(port, box_bg),
            fg=fg_color,
            relief="sunken",
            width=60
        )
        value_label.pack(side="left", padx=5)

        last_value_labels[port] = value_label

    # Live feed section for port 50050
    feed_frame = tk.LabelFrame(root, text="Live Feed from Port 50050", padx=10, pady=10, bg=bg_color, fg=fg_color)
    feed_frame.pack(padx=10, pady=10, fill="both", expand=True)

    live_feed_box = ScrolledText(
        feed_frame,
        height=15,
        wrap=tk.WORD,
        font=("Consolas", 11),
        bg=box_bg,
        fg=fg_color,
        insertbackground=fg_color,
    )
    live_feed_box.pack(fill="both", expand=True)

    # Show/Hide Console Button
    btn_frame = tk.Frame(root, bg=bg_color)
    btn_frame.pack(pady=5)

    toggle_btn = tk.Button(
        btn_frame,
        text="Show Console",
        bg=highlight_color,
        fg=fg_color,
        activebackground="#5e5e5e",
        activeforeground="#ffffff"
    )
    toggle_btn.config(command=lambda: toggle_console(toggle_btn))
    toggle_btn.pack()

    # Start UDP listener threads
    for port in UDP_PORTS:
        t = threading.Thread(target=udp_listener, args=(port,), daemon=True)
        t.start()

    root.mainloop()

# ======================== TAPO ========================
def init_tapo_devices():
    global tapo_manager

    async def setup():
        tapo_manager = await create_manager_from_config()
        await tapo_manager.blink("bulb_main_1", duration=2)
        await tapo_manager.blink("bulb_main_2", duration=2)
        await tapo_manager.blink("bulb_bed", duration=2)

    threading.Thread(target=lambda: asyncio.run(setup()), daemon=True).start()
# async def tapo_set():
#     client = ApiClient("osama.salahuddin@live.com", "TPl!nkR0uT3rM")
#     device = await client.l530("192.168.0.159")

#     await device.on()
#     await asyncio.sleep(2)
#     await device.off()


# ======================== MAIN ========================

if __name__ == "__main__":
    hide_console()
    # asyncio.run(tapo_set())
    init_tapo_devices()
    start_gui()
