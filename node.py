import grpc
from concurrent import futures
import time
import os
import glob
import sys
import json
import urllib.request
import storage_pb2
import storage_pb2_grpc

# Hide gRPC C++ errors from console
os.environ['GRPC_VERBOSITY'] = 'NONE'

SERVER_API_URL = "http://127.0.0.1:5000/register_node"

class StorageService(storage_pb2_grpc.StorageNodeServicer):
    def __init__(self, port):
        self.port = port
        self.storage_dir = f"node_storage_{port}"
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)

    def StoreChunk(self, request, context):
        path = f"{self.storage_dir}/{request.filename}.part{request.index}"
        with open(path, 'wb') as f:
            f.write(request.data)
        return storage_pb2.Response(success=True, message="Saved")

    def RetrieveChunk(self, request, context):
        path = f"{self.storage_dir}/{request.filename}.part{request.index}"
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = f.read()
            return storage_pb2.ChunkData(filename=request.filename, index=request.index, data=data)
        else:
            context.abort(grpc.StatusCode.NOT_FOUND, "Chunk not found")

    def DeleteChunk(self, request, context):
        pattern = f"{self.storage_dir}/{request.filename}.part*"
        for f in glob.glob(pattern):
            try: os.remove(f)
            except: pass
        print(f"[{self.port}] 🗑️ Deleted {request.filename}")
        return storage_pb2.Response(success=True, message="Deleted")

def register_with_server(port):
    try:
        data = json.dumps({'port': port}).encode('utf-8')
        req = urllib.request.Request(SERVER_API_URL, data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req)
        print(f"✅ Registered on port {port}")
    except:
        print(f"⚠️ Port {port} active (Server offline)")

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Auto-find port
    port = 50051
    while port < 50100:
        try:
            server.add_insecure_port(f'[::]:{port}')
            break
        except RuntimeError:
            port += 1
    
    storage_pb2_grpc.add_StorageNodeServicer_to_server(StorageService(port), server)
    server.start()
    print(f"🚀 Node started on port {port}")
    
    register_with_server(port)
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt: pass

if __name__ == '__main__':
    serve()