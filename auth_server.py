import grpc
from concurrent import futures
import bcrypt
import auth_pb2
import auth_pb2_grpc
import smtplib
import random
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURATION ---
PORT = 50050
CREDENTIALS_FILE = "credentials.txt"

# Update with your App Password if you want real emails
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "your_email@gmail.com"
SENDER_PASSWORD = "your_app_password" 

class AuthService(auth_pb2_grpc.UserServiceServicer):
    def __init__(self):
        self.otp_storage = {} 
        self.ensure_file_exists()

    def ensure_file_exists(self):
        if not os.path.exists(CREDENTIALS_FILE):
            with open(CREDENTIALS_FILE, 'w') as f: pass

    def get_user_data(self, username):
        with open(CREDENTIALS_FILE, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 3 and parts[0] == username:
                    return {'email': parts[1], 'hash': parts[2]}
        return None

    def save_user(self, username, email, hashed_pw):
        with open(CREDENTIALS_FILE, 'a') as f:
            f.write(f"{username},{email},{hashed_pw}\n")

    def send_email_otp(self, to_email, otp):
        """Try email, fallback to console print"""
        print(f"\n🔑 [CONSOLE OTP] Code for {to_email}: {otp}\n")
        try:
            if "your_app_password" in SENDER_PASSWORD: 
                raise Exception("No email config")
            
            msg = MIMEMultipart()
            msg['From'] = SENDER_EMAIL
            msg['To'] = to_email
            msg['Subject'] = "SkyDrive Login Code"
            msg.attach(MIMEText(f"Your Code: {otp}", 'plain'))

            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            server.quit()
            print(f"📧 Email sent to {to_email}")
        except Exception as e:
            print(f"⚠️ Email skipped (Check Console for Code): {e}")
        return True

    # --- gRPC HANDLERS ---

    def Register(self, request, context):
        if self.get_user_data(request.username):
            return auth_pb2.AuthResponse(success=False, message="User already exists")
        
        hashed = bcrypt.hashpw(request.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        self.save_user(request.username, request.email, hashed)
        print(f"🆕 Registered: {request.username}")
        return auth_pb2.AuthResponse(success=True, message="Registered")

    def Login(self, request, context):
        user = self.get_user_data(request.username)
        if not user:
            return auth_pb2.AuthResponse(success=False, message="User not found")

        if bcrypt.checkpw(request.password.encode('utf-8'), user['hash'].encode('utf-8')):
            otp = str(random.randint(100000, 999999))
            self.otp_storage[request.username] = otp
            self.send_email_otp(user['email'], otp)
            return auth_pb2.AuthResponse(success=True, message="OTP Sent")
        else:
            return auth_pb2.AuthResponse(success=False, message="Invalid Password")

    def VerifyOTP(self, request, context):
        stored_otp = self.otp_storage.get(request.username)
        if stored_otp and stored_otp == request.otp:
            del self.otp_storage[request.username]
            return auth_pb2.AuthResponse(success=True, message="Authenticated")
        return auth_pb2.AuthResponse(success=False, message="Invalid OTP")

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=5))
    auth_pb2_grpc.add_UserServiceServicer_to_server(AuthService(), server)
    server.add_insecure_port(f'[::]:{PORT}')
    print(f"🔐 Auth Service running on port {PORT}")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()