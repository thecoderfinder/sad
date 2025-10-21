# client.py
# Updated: Fixed file receive - always recv 8-byte length after JSON, only recv data if len > 0.
# This stops hanging/blinking. Improved error handling and logging. Password stripped and validated.
# Files save to current dir. Run server first, copy IP from its output, paste here.

import socket
import json
import struct
import os
import sys
import logging

# Simple logging for client
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def send_command(host='127.0.0.1', port=12345, password=None, command=None, **kwargs):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(10)  # 10s timeout to prevent hangs
        sock.connect((host, port))
        request = {"command": command, "password": password.strip() if password else "", **kwargs}
        request_json = json.dumps(request)
        sock.send(request_json.encode('utf-8'))
        response_data = sock.recv(4096).decode('utf-8')
        response = json.loads(response_data)
        # Always recv file length header
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
            filename = response.get('filename')
            if filename:
                local_path = os.path.join(os.getcwd(), filename)
                with open(local_path, 'wb') as f:
                    f.write(file_data)
                response["messages"].append(f"File saved: {local_path}")
                logging.info(f"Received file: {filename} ({file_length} bytes)")
        return response
    except socket.timeout:
        return {"status": "error", "messages": ["Connection timed out. Server may not be running."]}
    except socket.error as e:
        return {"status": "error", "messages": [f"Connection failed: {e}. Is the server running on {host}:{port}?"]}
    except json.JSONDecodeError as e:
        return {"status": "error", "messages": [f"Invalid response: {e}"]}
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return {"status": "error", "messages": [f"Unexpected error: {e}"]}
    finally:
        sock.close()

if __name__ == "__main__":
    host = input("Enter server host (default 127.0.0.1): ").strip() or '127.0.0.1'
    password = input("Enter password: ").strip()
    if not password:
        print("No password provided. Exiting.")
        sys.exit(1)
    logging.info(f"Connecting to {host}:12345 with password length {len(password)}")
    while True:
        print("\n--- REMOTE CLIENT ---")
        print("1) Take screenshot")
        print("2) Typed capture (send text)")
        print("3) List processes")
        print("4) Close process (enter name)")
        print("5) Generate harmless files")
        print("6) Open program (enter cmd)")
        print("7) Take webcam photo")
        print("8) Toggle webcam recording")
        print("9) Exit")
        choice = input("Enter choice: ").strip()
        if choice == "9":
            break
        resp = None
        try:
            if choice == "1":
                resp = send_command(host, command="take_screenshot", password=password)
            elif choice == "2":
                text = input("Text to send: ").strip()
                resp = send_command(host, command="typed_capture", text=text, password=password)
            elif choice == "3":
                limit_str = input("Limit (default 300): ").strip()
                limit = int(limit_str) if limit_str else 300
                resp = send_command(host, command="list_processes", limit=limit, password=password)
            elif choice == "4":
                name = input("Process name: ").strip()
                if not name:
                    print("No name provided.")
                    continue
                resp = send_command(host, command="close_process", name=name, password=password)
            elif choice == "5":
                resp = send_command(host, command="generate_harmless_files", password=password)
            elif choice == "6":
                cmd = input("Command/path: ").strip()
                if not cmd:
                    print("No command provided.")
                    continue
                resp = send_command(host, command="open_program", cmd=cmd, password=password)
            elif choice == "7":
                resp = send_command(host, command="take_webcam_photo", password=password)
            elif choice == "8":
                resp = send_command(host, command="toggle_webcam_recording", password=password)
            else:
                print("Unknown option.")
                continue
            status = resp.get("status", "unknown")
            messages = resp.get("messages", ["No response."])
            print(f"\n{'[OK]' if status == 'ok' else '[ERROR]'}:\n" + "\n".join(messages))
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break
        except Exception as e:
            print(f"Client error: {e}")