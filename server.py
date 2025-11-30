import socket
import threading
import json
import time
import subprocess
import sys
import logging
import os
import random
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS

# --- CONFIGURATION ---
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) 

NODE_PORT = 6000
API_PORT = 5000
REPLICATION_FACTOR = 2 
DATA_FILE = "system_data.json"

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 
CORS(app)

class NetworkState:
    def __init__(self):
        self.nodes = {} 
        self.files = {} 
        self.assigned_ips = 1
        self.user_quota = 5 * 1024 * 1024 * 1024 
        self.lock = threading.Lock() 
        self.save_lock = threading.Lock()
        self.load_system() 

    def save_system(self):
        with self.save_lock: 
            data = {
                'files': {k: {'size': v['size'], 'total_chunks': v.get('total_chunks', 0), 'locations': list(v['locations'])} for k, v in self.files.items()},
                'quota': self.user_quota
            }
            try:
                with open(DATA_FILE + ".tmp", 'w') as f: json.dump(data, f)
                if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
                os.rename(DATA_FILE + ".tmp", DATA_FILE)
            except Exception as e: print(f"[System] Save failed: {e}")

    def load_system(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r') as f:
                    data = json.load(f)
                    self.user_quota = data.get('quota', 5 * 1024 * 1024 * 1024)
                    saved_files = data.get('files', {})
                    for fname, info in saved_files.items():
                        self.files[fname] = {
                            'size': info['size'],
                            'total_chunks': info.get('total_chunks', 0),
                            'locations': set(info['locations'])
                        }
            except: pass

state = NetworkState()

# --- FIXED CONNECTION HANDLER ---
def handle_node_connection(conn, addr):
    """
    Handles the initial handshake.
    CRITICAL FIX: Once registered, we EXIT this thread but keep the socket OPEN.
    We do NOT enter a 'while True' loop, because that loop steals data from the download function.
    """
    node_id = None
    try:
        # 1. Handshake
        data = conn.recv(1024).decode()
        reg_info = json.loads(data)
        node_id = reg_info['node_id']
        
        # 2. Register Node
        with state.lock:
            fake_ip = f"192.168.1.{state.assigned_ips}"
            state.assigned_ips += 1
            state.nodes[node_id] = {
                'conn': conn, # Socket remains open here
                'ip': fake_ip,
                'usage': 0, 
                'capacity': reg_info['capacity'],
                'node_lock': threading.Lock()
            }
        
        # 3. Send ACK
        conn.send(json.dumps({'status': 'assigned', 'ip': fake_ip}).encode())
        print(f"[System] Node connected: {node_id}")
        
        # 4. CRITICAL: Do not close conn, do not loop. Just exit thread.
        # The socket object is now safely stored in state.nodes and will be used by API threads.
        return 

    except Exception as e:
        print(f"[System] Connection failed: {e}")
        try: conn.close()
        except: pass

def node_server_thread():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', NODE_PORT))
    server.listen(10)
    print(f"[System] Cloud Core running on port {NODE_PORT}")
    while True:
        try:
            conn, addr = server.accept()
            # Start a thread just for handshake
            t = threading.Thread(target=handle_node_connection, args=(conn, addr), daemon=True)
            t.start()
        except Exception as e:
            print(f"[System] Accept error: {e}")

# --- API ENDPOINTS ---

@app.errorhandler(500)
def handle_500(e):
    traceback.print_exc()
    return jsonify({'error': 'Internal Server Error', 'details': str(e)}), 500

@app.route('/status', methods=['GET'])
def get_status():
    with state.lock:
        # Lazy Cleanup: Check if nodes are dead only when asked
        # (This is simpler than a heartbeat loop that causes race conditions)
        dead_nodes = []
        for nid, node in state.nodes.items():
            try:
                # peek to see if connection is dead (optional, risky on windows)
                pass 
            except:
                dead_nodes.append(nid)
        
        total_used = sum(f['size'] for f in state.files.values())
        return jsonify({
            'used': total_used,
            'quota': state.user_quota,
            'nodes_online': len(state.nodes),
            'files': list(state.files.keys())
        })

@app.route('/upload_chunk', methods=['POST'])
def upload_chunk():
    try:
        file = request.files['chunk']
        filename = request.form['filename']
        chunk_index = int(request.form['index'])
        total_chunks = int(request.form['total_chunks'])
        file_size = int(request.form['total_size'])
        chunk_data = file.read()
        
        target_nodes_ids = []
        
        with state.lock:
            available_nodes = list(state.nodes.keys())
            if not available_nodes: return jsonify({'error': 'No Nodes Online'}), 503
            
            # Deterministic Shuffle based on filename for consistency, or random
            random.shuffle(available_nodes) 
            target_nodes_ids = available_nodes[:REPLICATION_FACTOR]
            
            if filename not in state.files:
                state.files[filename] = {'size': file_size, 'locations': set(), 'total_chunks': total_chunks}

        success_count = 0
        nodes_to_remove = []

        for nid in target_nodes_ids:
            node = None
            with state.lock:
                if nid in state.nodes: node = state.nodes[nid]

            if node:
                with node['node_lock']:
                    try:
                        header = json.dumps({'cmd': 'store', 'file': filename, 'index': chunk_index, 'size': len(chunk_data)})
                        node['conn'].sendall(header.encode() + b'\n')
                        node['conn'].sendall(chunk_data)
                        node['usage'] += len(chunk_data)
                        success_count += 1
                    except (BrokenPipeError, ConnectionResetError): 
                        print(f"[System] Node {nid} died during upload.")
                        nodes_to_remove.append(nid)
                    except Exception as e:
                        print(f"[System] Upload error to {nid}: {e}")

        # Cleanup dead nodes
        if nodes_to_remove:
            with state.lock:
                for nid in nodes_to_remove:
                    if nid in state.nodes: del state.nodes[nid]
                
        # Update locations
        if success_count > 0:
            with state.lock:
                if filename in state.files:
                    for nid in target_nodes_ids:
                        if nid not in nodes_to_remove:
                            state.files[filename]['locations'].add(nid)

        if chunk_index == total_chunks - 1 or chunk_index == 0:
            state.save_system()
            if chunk_index == total_chunks - 1:
                print(f"[Traffic] Upload Complete: {filename}")

        if success_count == 0:
            return jsonify({'error': 'All selected nodes failed'}), 500

        return jsonify({'status': 'ok'})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/download_chunk', methods=['GET'])
def download_chunk():
    try:
        filename = request.args.get('filename')
        index = int(request.args.get('index'))
        
        target_node = None
        with state.lock:
            if filename not in state.files: return jsonify({'error': 'File not found'}), 404
            potential_nodes = list(state.files[filename]['locations'])
            online_sources = [n for n in potential_nodes if n in state.nodes]
            if not online_sources: return jsonify({'error': 'Unavailable'}), 503
            
            # Pick random to load balance
            target_node = state.nodes[random.choice(online_sources)]
        
        # We must lock the node during transaction to prevent race conditions
        with target_node['node_lock']:
            try:
                # 1. Send Request
                req = json.dumps({'cmd': 'retrieve', 'file': filename, 'index': index})
                target_node['conn'].sendall(req.encode() + b'\n')
                
                # 2. Receive Header (Blocking, but safe now that we removed the background loop)
                header_bytes = target_node['conn'].recv(1024) 
                
                if not header_bytes:
                    raise ConnectionResetError("Node closed connection")

                if b'\n' in header_bytes:
                    header, remainder = header_bytes.split(b'\n', 1)
                    meta = json.loads(header.decode())
                    
                    if meta.get('status') == 'error':
                        print(f"[Error] Node reported missing chunk: {filename} #{index}")
                        return jsonify({'error': 'Chunk missing on node'}), 404
                    
                    size = meta['size']
                    data = remainder
                    
                    # 3. Receive Body
                    while len(data) < size: 
                        chunk = target_node['conn'].recv(1024 * 1024)
                        if not chunk: break
                        data += chunk
                    
                    return data
                else:
                    return jsonify({'error': 'Invalid header from node'}), 502

            except (BrokenPipeError, ConnectionResetError):
                # Handle Node Death gracefully
                with state.lock:
                    # Find ID of this node object
                    dead_id = None
                    for nid, n in state.nodes.items():
                        if n == target_node: dead_id = nid
                    if dead_id: del state.nodes[dead_id]
                return jsonify({'error': 'Node died during transfer'}), 503
            except Exception as e: 
                print(f"[Download Error] {e}")
                return jsonify({'error': f"Node error: {str(e)}"}), 502

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/delete_file', methods=['DELETE'])
def delete_file():
    filename = request.args.get('filename')
    with state.lock:
        if filename in state.files:
            for nid in state.files[filename]['locations']:
                if nid in state.nodes:
                    try:
                        node = state.nodes[nid]
                        with node['node_lock']:
                             node['conn'].sendall(json.dumps({'cmd': 'delete', 'file': filename}).encode() + b'\n')
                    except: pass
            del state.files[filename]
            state.save_system()
            print(f"[Admin] Deleted: {filename}")
    return jsonify({'status': 'deleted'})

@app.route('/file_info', methods=['GET'])
def file_info():
    filename = request.args.get('filename')
    with state.lock:
        if filename in state.files:
            info = state.files[filename].copy()
            info['locations'] = list(info['locations'])
            return jsonify(info)
        return jsonify({'error': 'Not found'}), 404

@app.route('/add_space', methods=['POST'])
def add_space():
    with state.lock:
        state.user_quota += 5 * 1024 * 1024 * 1024
        state.save_system()
    subprocess.Popen([sys.executable, 'node.py'])
    return jsonify({'status': 'upgraded'})

if __name__ == '__main__':
    t = threading.Thread(target=node_server_thread, daemon=True)
    t.start()
    print(f"[System] API running on http://localhost:{API_PORT}")
    app.run(port=API_PORT, debug=True, use_reloader=False, threaded=True)