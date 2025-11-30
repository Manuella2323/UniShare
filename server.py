import threading
import json
import time
import subprocess
import sys
import logging
import os
import random
import traceback
import grpc 
import storage_pb2 
import storage_pb2_grpc 
from flask import Flask, request, jsonify
from flask_cors import CORS

# --- CONFIGURATION ---
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) 

API_PORT = 5000
REPLICATION_FACTOR = 2 
DATA_FILE = "system_data.json"

KNOWN_NODE_PORTS = [] 

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 
CORS(app)

class NetworkState:
    def __init__(self):
        self.files = {} 
        self.user_quota = 5 * 1024 * 1024 * 1024 
        self.lock = threading.Lock() 
        self.save_lock = threading.Lock()
        self.load_system() 

    def save_system(self):
        with self.save_lock: 
            data = {
                'files': {k: {'size': v['size'], 'total_chunks': v.get('total_chunks', 0), 'locations': list(v['locations'])} for k, v in self.files.items()},
                'quota': self.user_quota,
                'nodes': KNOWN_NODE_PORTS 
            }
            try:
                with open(DATA_FILE + ".tmp", 'w') as f: json.dump(data, f)
                if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
                os.rename(DATA_FILE + ".tmp", DATA_FILE)
            except Exception as e: print(f"[System] Save failed: {e}")

    def load_system(self):
        global KNOWN_NODE_PORTS
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r') as f:
                    data = json.load(f)
                    self.user_quota = data.get('quota', 5 * 1024 * 1024 * 1024)
                    KNOWN_NODE_PORTS = data.get('nodes', [])
                    saved_files = data.get('files', {})
                    for fname, info in saved_files.items():
                        self.files[fname] = {
                            'size': info['size'],
                            'total_chunks': info.get('total_chunks', 0),
                            'locations': set(info['locations'])
                        }
            except: pass

state = NetworkState()

# --- AUTO LAUNCHER ---
def launch_initial_nodes():
    time.sleep(1)
    if len(KNOWN_NODE_PORTS) == 0:
        print("[Auto-Scale] First run detected. Launching 3 nodes...")
        for _ in range(3):
            subprocess.Popen([sys.executable, 'node.py'])
            time.sleep(0.5)
    else:
        print(f"[System] Found {len(KNOWN_NODE_PORTS)} nodes in history. Launching them...")
        for _ in range(len(KNOWN_NODE_PORTS)):
             subprocess.Popen([sys.executable, 'node.py'])
             time.sleep(0.2)

# --- API ENDPOINTS ---

@app.route('/register_node', methods=['POST'])
def register_node():
    data = request.json
    port = data.get('port')
    if port and port not in KNOWN_NODE_PORTS:
        KNOWN_NODE_PORTS.append(port)
        state.save_system()
        print(f"[Discovery] Node Registered: Port {port}")
    return jsonify({'status': 'registered'})

@app.route('/status', methods=['GET'])
def get_status():
    with state.lock:
        real_online = 0
        for port in KNOWN_NODE_PORTS:
            # Simple check or assume online
            real_online += 1
            
        total_used = sum(f['size'] for f in state.files.values())
        return jsonify({
            'used': total_used,
            'quota': state.user_quota,
            'nodes_online': real_online,
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
        
        target_addresses = []
        
        with state.lock:
            if not KNOWN_NODE_PORTS: return jsonify({'error': 'No Nodes'}), 503
            available = list(KNOWN_NODE_PORTS)
            random.shuffle(available)
            selected = available[:REPLICATION_FACTOR]
            target_addresses = [f'localhost:{p}' for p in selected]
            
            if filename not in state.files:
                state.files[filename] = {'size': file_size, 'locations': set(), 'total_chunks': total_chunks}

        success_count = 0
        for address in target_addresses:
            try:
                with grpc.insecure_channel(address) as channel:
                    stub = storage_pb2_grpc.StorageNodeStub(channel)
                    resp = stub.StoreChunk(storage_pb2.ChunkData(filename=filename, index=chunk_index, data=chunk_data))
                    if resp.success:
                        success_count += 1
                        with state.lock:
                            if filename in state.files: state.files[filename]['locations'].add(address)
            except: pass

        if chunk_index == total_chunks - 1 or chunk_index == 0:
            state.save_system()
            if chunk_index == total_chunks - 1: print(f"[Traffic] Upload Complete: {filename}")

        if success_count == 0: return jsonify({'error': 'Nodes failed'}), 500
        return jsonify({'status': 'ok'})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/download_chunk', methods=['GET'])
def download_chunk():
    try:
        filename = request.args.get('filename')
        index = int(request.args.get('index'))
        
        target = None
        with state.lock:
            if filename not in state.files: return jsonify({'error': 'File not found'}), 404
            locs = list(state.files[filename]['locations'])
            if not locs: return jsonify({'error': 'Unavailable'}), 503
            target = random.choice(locs)
        
        try:
            with grpc.insecure_channel(target) as channel:
                stub = storage_pb2_grpc.StorageNodeStub(channel)
                resp = stub.RetrieveChunk(storage_pb2.ChunkRequest(filename=filename, index=index))
                return resp.data
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND: return jsonify({'error': 'Missing'}), 404
            return jsonify({'error': 'Node Error'}), 502

    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/delete_file', methods=['DELETE'])
def delete_file():
    filename = request.args.get('filename')
    with state.lock:
        if filename in state.files:
            for addr in state.files[filename]['locations']:
                try:
                    with grpc.insecure_channel(addr) as ch:
                        stub = storage_pb2_grpc.StorageNodeStub(ch)
                        stub.DeleteChunk(storage_pb2.ChunkRequest(filename=filename, index=0))
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
    print("[Auto-Scale] Launching new node...")
    subprocess.Popen([sys.executable, 'node.py'])
    return jsonify({'status': 'upgraded'})

if __name__ == '__main__':
    # Auto-launch nodes in background
    threading.Thread(target=launch_initial_nodes, daemon=True).start()
    print(f"[System] API running on http://localhost:{API_PORT}")
    app.run(port=API_PORT, debug=True, use_reloader=False, threaded=True)