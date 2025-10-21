# server.py
# Simple remote helper server that prints a short connection code (3 digits + 2 letters).
# RUN ONLY on machines YOU OWN or where you have EXPLICIT permission.
# Listens on 0.0.0.0:12345.
# Requirements: pip install pyautogui psutil  (opencv-python optional)

import socket, json, struct, threading, io, os, sys, logging, time, random, string
from pathlib import Path
from datetime import datetime

# Basic logging
DL = Path.cwd()
log_file = DL / f"server_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
logging.getLogger().addHandler(console)

PORT = 12345

def gen_code():
    digits = ''.join(random.choices('0123456789', k=3))
    letters = ''.join(random.choices(string.ascii_letters, k=2))
    return digits + letters

CODE = gen_code()

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't need to be reachable; used to pick right interface
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# Minimal features: probe (for discovery) + take_screenshot example that returns bytes
try:
    import pyautogui
    PY_AVAILABLE = True
except Exception:
    PY_AVAILABLE = False

def take_screenshot():
    if not PY_AVAILABLE:
        return {"status": "error", "messages": ["pyautogui not installed on server."]}
    try:
        img = pyautogui.screenshot()
        b = io.BytesIO()
        img.save(b, format='PNG')
        data = b.getvalue()
        return {"status":"ok","messages":["screenshot"], "file_data": data, "filename": f"screenshot_{int(time.time())}.png"}
    except Exception as e:
        logging.exception("screenshot failed")
        return {"status":"error","messages":[f"screenshot failed: {e}"]}

def handle_command(req):
    cmd = req.get("command","").strip()
    if cmd == "probe":
        # discovery: client provides code to match
        provided = req.get("code","")
        if provided == CODE:
            return {"status":"ok","messages":["probe ok","code matched"], "server_ip": get_local_ip()}
        else:
            return {"status":"error","messages":["probe mismatch"]}
    elif cmd == "take_screenshot":
        return take_screenshot()
    else:
        return {"status":"error","messages":[f"unknown command {cmd}"]}

def socket_handler(conn, addr):
    logging.info(f"client connected: {addr}")
    try:
        # read single request per connection (simple)
        data = conn.recv(4096)
        if not data:
            return
        try:
            req = json.loads(data.decode('utf-8'))
        except Exception:
            logging.warning("invalid json received")
            return
        resp = handle_command(req)
        # send JSON without file_data
        json_resp = {k:v for k,v in resp.items() if k != "file_data"}
        conn.send(json.dumps(json_resp).encode('utf-8'))
        # then always send 8-byte length header followed by optional file_data
        file_bytes = resp.get("file_data") or b""
        conn.send(struct.pack('Q', len(file_bytes)))
        if file_bytes:
            conn.sendall(file_bytes)
            logging.info(f"sent file {resp.get('filename')}")
    except Exception as e:
        logging.exception("socket handler error")
    finally:
        try:
            conn.close()
        except:
            pass
        logging.info("client disconnected")

def start_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', PORT))
    s.listen(5)
    return s

if __name__ == "__main__":
    print("!!! SECURITY: Run this ONLY on machines you OWN or with explicit permission. No auth.")
    ip = get_local_ip()
    print(f"Server local IP: {ip}:{PORT}")
    print(f"Connection code: {CODE}")
    print("Give that code to the client (or use IP). Server starting...")

    server_sock = start_server()
    try:
        while True:
            conn, addr = server_sock.accept()
            t = threading.Thread(target=socket_handler, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("Shutting down server.")
    finally:
        server_sock.close()
