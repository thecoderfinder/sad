# client.py
# Client that either accepts direct IP OR a 5-char short code (3 digits + 2 letters).
# If you provide a short code, the client scans the local /24 subnet for the server.
# Once connected, it can issue commands (example: take_screenshot).
# Save received files to ./received_files

import socket, json, struct, os, sys, time, logging, re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
RECV_DIR = Path.cwd() / "received_files"
RECV_DIR.mkdir(exist_ok=True)

PORT = 12345
SHORTCODE_RE = re.compile(r'^\d{3}[A-Za-z]{2}$')

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def send_request(host, request, timeout=1.0):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, PORT))
        sock.send(json.dumps(request).encode('utf-8'))
        # receive JSON response
        resp_json = sock.recv(4096).decode('utf-8')
        resp = json.loads(resp_json)
        # read 8-byte length header
        header = sock.recv(8)
        if len(header) != 8:
            raise Exception("invalid length header")
        file_len = struct.unpack('Q', header)[0]
        if file_len > 0:
            data = b''
            remaining = file_len
            while remaining > 0:
                chunk = sock.recv(min(4096, remaining))
                if not chunk:
                    raise Exception("incomplete file transfer")
                data += chunk
                remaining -= len(chunk)
            fname = resp.get("filename") or f"file_{int(time.time())}"
            outp = RECV_DIR / fname
            with open(outp, 'wb') as f:
                f.write(data)
            messages = resp.get("messages", [])
            messages.append(f"File saved: {outp}")
            resp["messages"] = messages
        sock.close()
        return resp
    except socket.timeout:
        return {"status":"error","messages":[f"timeout connecting to {host}:{PORT}"]}
    except Exception as e:
        return {"status":"error","messages":[f"connection failed to {host}:{PORT}: {e}"]}

def scan_for_code(code):
    # derive base /24 from local IP
    local_ip = get_local_ip()
    parts = local_ip.split('.')
    if len(parts) != 4:
        print("Could not determine local subnet.")
        return None
    base = '.'.join(parts[:3])
    print(f"Scanning subnet {base}.1-254 for code {code} (this may take a while)...")
    for i in range(1, 255):
        target = f"{base}.{i}"
        # skip self quickly if matches
        resp = send_request(target, {"command":"probe", "code": code}, timeout=0.4)
        if resp.get("status") == "ok":
            print(f"Found server at {target}")
            return target
    return None

def main_menu(server_ip):
    print(f"Connected to server {server_ip}:{PORT}")
    while True:
        print("\n1) Take screenshot (server -> saved here)")
        print("9) Exit")
        choice = input("Choice: ").strip()
        if choice == "9":
            break
        if choice == "1":
            resp = send_request(server_ip, {"command":"take_screenshot"}, timeout=5.0)
            for m in resp.get("messages", []):
                print(m)
        else:
            print("Unknown option.")

if __name__ == "__main__":
    user_in = input("Enter server IP (e.g. 192.168.1.100) OR short code (e.g. 123Ab): ").strip()
    if not user_in:
        print("No input. Exiting.")
        sys.exit(1)

    server_ip = None
    if SHORTCODE_RE.match(user_in):
        # treat as code, scan local subnet
        print("Treating input as short code; scanning local subnet...")
        found = scan_for_code(user_in)
        if not found:
            print("Failed to connect: no server with that code found on local subnet.")
            sys.exit(1)
        server_ip = found
    else:
        # assume direct IP
        server_ip = user_in

    # quick probe to confirm
    probe = send_request(server_ip, {"command":"probe", "code": ""}, timeout=1.0)
    # server will likely reject empty code; but probe success isn't necessary here
    # proceed to menu
    main_menu(server_ip)
