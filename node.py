import socket
import json
import uuid
import os
import threading
import time
import glob

SERVER_IP = '127.0.0.1'
SERVER_PORT = 6000

def get_existing_node_dirs():
    return [d for d in os.listdir('.') if os.path.isdir(d) and d.startswith('node_storage_')]

def run_single_node(node_id, is_new=False):
    storage_dir = f"node_storage_{node_id}" 
    if not os.path.exists(storage_dir):
        os.makedirs(storage_dir)

    print(f"[Launcher] {'Resurrecting' if not is_new else 'Starting'} Node {node_id}...")

    while True:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((SERVER_IP, SERVER_PORT))
            
            # Register
            reg = json.dumps({'node_id': node_id, 'capacity': 10 * 1024 * 1024 * 1024})
            sock.send(reg.encode())
            sock.recv(1024) # Wait for ACK
            
            if is_new: print(f"✅ [{node_id}] Online.")

            buffer = b""
            while True:
                # 1. READ HEADER (Small chunks)
                while b'\n' not in buffer:
                    chunk = sock.recv(4096)
                    if not chunk: raise Exception("Disconnect")
                    buffer += chunk
                
                header_part, buffer = buffer.split(b'\n', 1)
                
                try:
                    cmd = json.loads(header_part.decode())
                    
                    if cmd['cmd'] == 'store':
                        # 2. READ BODY (Large chunks - Optimized loop)
                        payload_size = cmd['size']
                        while len(buffer) < payload_size:
                            # Read up to 1MB at a time for speed
                            buffer += sock.recv(1024 * 1024) 
                        
                        file_data = buffer[:payload_size]
                        buffer = buffer[payload_size:]
                        
                        fname = f"{cmd['file']}.part{cmd['index']}"
                        with open(os.path.join(storage_dir, fname), 'wb') as f:
                            f.write(file_data)
                        
                        # NO PRINTING here for speed.

                    elif cmd['cmd'] == 'retrieve':
                        fname = f"{cmd['file']}.part{cmd['index']}"
                        path = os.path.join(storage_dir, fname)
                        if os.path.exists(path):
                            with open(path, 'rb') as f:
                                raw = f.read()
                            header = json.dumps({'size': len(raw)})
                            sock.sendall(header.encode() + b'\n')
                            sock.sendall(raw)
                        else:
                            header = json.dumps({'status': 'error', 'error': 'not_found'})
                            sock.sendall(header.encode() + b'\n')

                    elif cmd['cmd'] == 'delete':
                        pattern = os.path.join(storage_dir, f"{cmd['file']}.part*")
                        for f in glob.glob(pattern): os.remove(f)

                except Exception:
                    pass # Ignore malformed packets to keep node alive

        except Exception:
            time.sleep(5)
        finally:
            if sock: sock.close()

if __name__ == '__main__':
    existing_dirs = get_existing_node_dirs()
    threads = []
    
    for d in existing_dirs:
        node_id = d.replace('node_storage_', '')
        t = threading.Thread(target=run_single_node, args=(node_id, False), daemon=True)
        t.start()
        threads.append(t)
        
    nodes_needed = 3 - len(existing_dirs)
    for i in range(nodes_needed):
        new_id = f"node_{uuid.uuid4().hex[:6]}"
        t = threading.Thread(target=run_single_node, args=(new_id, True), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.5)

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt: pass