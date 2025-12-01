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
# Import BOTH protocol definitions
import storage_pb2 
import storage_pb2_grpc 
import auth_pb2
import auth_pb2_grpc
from flask import Flask, request, jsonify
from flask_cors import CORS
from collections import defaultdict

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) 

API_PORT = 5000
AUTH_PORT = 50050 # Where auth_server.py is running
REPLICATION_FACTOR = 2 
DATA_FILE = "system_data.json"
DEFAULT_QUOTA = 5 * 1024 * 1024 * 1024

KNOWN_NODE_PORTS = [] 

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 
CORS(app)

class NetworkState:
    def __init__(self):
        self.user_files = defaultdict(dict) 
        self.user_quotas = defaultdict(lambda: DEFAULT_QUOTA)
        self.lock = threading.Lock() 
        self.save_lock = threading.Lock()
        self.load_system() 

    def save_system(self):
        with self.save_lock: 
            export_files = {u: files for u, files in self.user_files.items()}
            export_quotas = {u: q for u, q in self.user_quotas.items()}
            data = {
                'users': export_files,
                'quotas': export_quotas,
                'nodes': KNOWN_NODE_PORTS 
            }
            try:
                with open(DATA_FILE + ".tmp", 'w') as f:
                    json.dump(data, f, default=lambda o: list(o) if isinstance(o, set) else o)
                if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
                os.rename(DATA_FILE + ".tmp", DATA_FILE)
            except: pass

    def load_system(self):
        global KNOWN_NODE_PORTS
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r') as f:
                    data = json.load(f)
                    KNOWN_NODE_PORTS = data.get('nodes', [])
                    raw_users = data.get('users', {})
                    for user, files in raw_users.items():
                        for fname, info in files.items():
                            self.user_files[user][fname] = {
                                'size': info['size'],
                                'total_chunks': info.get('total_chunks', 0),
                                'locations': set(info['locations'])
                            }
                    raw_quotas = data.get('quotas', {})
                    for user, q in raw_quotas.items():
                        self.user_quotas[user] = q
            except: pass

state = NetworkState()

# --- AUTO LAUNCHER ---
def launch_initial_nodes():
    time.sleep(1)
    if len(KNOWN_NODE_PORTS) == 0:
        print("[Auto-Scale] First run. Launching 3 nodes...")
        for _ in range(3):
            subprocess.Popen([sys.executable, 'node.py'])
            time.sleep(0.5)
    else:
        print(f"[System] Restoring {len(KNOWN_NODE_PORTS)} nodes...")
        for _ in range(len(KNOWN_NODE_PORTS)):
             subprocess.Popen([sys.executable, 'node.py'])
             time.sleep(0.2)

# --- AUTH ROUTES (Proxy to gRPC) ---

def get_auth_stub():
    channel = grpc.insecure_channel(f'localhost:{AUTH_PORT}')
    return auth_pb2_grpc.UserServiceStub(channel)

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    try:
        stub = get_auth_stub()
        resp = stub.Register(auth_pb2.RegisterRequest(
            username=data['username'], 
            password=data['password'], 
            email=data['email']
        ))
        return jsonify({'success': resp.success, 'message': resp.message})
    except grpc.RpcError as e:
        return jsonify({'success': False, 'message': 'Auth Service Unavailable'}), 503
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    try:
        stub = get_auth_stub()
        resp = stub.Login(auth_pb2.LoginRequest(
            username=data['username'], 
            password=data['password']
        ))
        return jsonify({'success': resp.success, 'message': resp.message})
    except grpc.RpcError:
        return jsonify({'success': False, 'message': 'Auth Service Unavailable'}), 503

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    data = request.json
    try:
        stub = get_auth_stub()
        resp = stub.VerifyOTP(auth_pb2.OTPRequest(
            username=data['username'], 
            otp=data['otp']
        ))
        return jsonify({'success': resp.success, 'message': resp.message})
    except grpc.RpcError:
        return jsonify({'success': False, 'message': 'Auth Service Unavailable'}), 503

# --- FILE ROUTES ---

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
    user = request.args.get('username')
    if not user: return jsonify({'error': 'User required'}), 400
    with state.lock:
        total_used = sum(f['size'] for f in state.user_files[user].values())
        return jsonify({
            'used': total_used,
            'quota': state.user_quotas[user],
            'nodes_online': len(KNOWN_NODE_PORTS),
            'files': list(state.user_files[user].keys())
        })

@app.route('/upload_chunk', methods=['POST'])
def upload_chunk():
    try:
        user = request.form['username']
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
            
            if filename not in state.user_files[user]:
                state.user_files[user][filename] = {'size': file_size, 'locations': set(), 'total_chunks': total_chunks}

        success_count = 0
        for address in target_addresses:
            try:
                with grpc.insecure_channel(address) as channel:
                    stub = storage_pb2_grpc.StorageNodeStub(channel)
                    resp = stub.StoreChunk(storage_pb2.ChunkData(filename=f"{user}_{filename}", index=chunk_index, data=chunk_data))
                    if resp.success:
                        success_count += 1
                        with state.lock:
                            if filename in state.user_files[user]: 
                                state.user_files[user][filename]['locations'].add(address)
            except: pass

        if chunk_index == total_chunks - 1 or chunk_index == 0:
            state.save_system()

        if success_count == 0: return jsonify({'error': 'Nodes failed'}), 500
        return jsonify({'status': 'ok'})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/download_chunk', methods=['GET'])
def download_chunk():
    try:
        user = request.args.get('username')
        filename = request.args.get('filename')
        index = int(request.args.get('index'))
        
        target = None
        with state.lock:
            if filename not in state.user_files[user]: return jsonify({'error': 'File not found'}), 404
            locs = list(state.user_files[user][filename]['locations'])
            if not locs: return jsonify({'error': 'Unavailable'}), 503
            target = random.choice(locs)
        
        try:
            with grpc.insecure_channel(target) as channel:
                stub = storage_pb2_grpc.StorageNodeStub(channel)
                resp = stub.RetrieveChunk(storage_pb2.ChunkRequest(filename=f"{user}_{filename}", index=index))
                return resp.data
        except grpc.RpcError: return jsonify({'error': 'Node Error'}), 502
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/delete_file', methods=['DELETE'])
def delete_file():
    user = request.args.get('username')
    filename = request.args.get('filename')
    with state.lock:
        if filename in state.user_files[user]:
            for addr in state.user_files[user][filename]['locations']:
                try:
                    with grpc.insecure_channel(addr) as ch:
                        stub = storage_pb2_grpc.StorageNodeStub(ch)
                        stub.DeleteChunk(storage_pb2.ChunkRequest(filename=f"{user}_{filename}", index=0))
                except: pass
            del state.user_files[user][filename]
            state.save_system()
    return jsonify({'status': 'deleted'})

@app.route('/file_info', methods=['GET'])
def file_info():
    user = request.args.get('username')
    filename = request.args.get('filename')
    with state.lock:
        if filename in state.user_files[user]:
            info = state.user_files[user][filename].copy()
            info['locations'] = list(info['locations'])
            return jsonify(info)
        return jsonify({'error': 'Not found'}), 404

@app.route('/add_space', methods=['POST'])
def add_space():
    user = request.json.get('username')
    with state.lock:
        state.user_quotas[user] += 5 * 1024 * 1024 * 1024
        state.save_system()
    subprocess.Popen([sys.executable, 'node.py'])
    return jsonify({'status': 'upgraded'})

if __name__ == '__main__':
    threading.Thread(target=launch_initial_nodes, daemon=True).start()
    print(f"[System] API running on http://localhost:{API_PORT}")
    app.run(port=API_PORT, debug=True, use_reloader=False, threaded=True)