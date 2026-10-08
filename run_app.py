"""
MediConnect EHR All-in-One Launcher
Starts the backend server, verifies dependencies, initializes the database, and launches the site in your browser.
Usage: python run_app.py
"""

import sys
import os
import time
import socket
import webbrowser
import threading
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"

def check_and_install_dependencies():
    """Verify essential packages and install from requirements.txt if needed."""
    required = ["fastapi", "uvicorn", "pydantic", "pandas", "sklearn", "joblib"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print(f"[!] Missing required package(s): {', '.join(missing)}")
        req_file = os.path.join(BASE_DIR, "requirements.txt")
        if os.path.exists(req_file):
            print(f"[*] Installing packages from {req_file}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file])
            print("[+] Dependencies installed successfully.\n")

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if the given port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0

def free_port_if_needed(port: int):
    """If port is occupied on Windows, attempt to terminate the stale process."""
    if not is_port_in_use(port):
        return
    
    if sys.platform == "win32":
        try:
            output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
            for line in output.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in parts:
                    pid = parts[-1]
                    if pid != str(os.getpid()):
                        print(f"[*] Port {port} occupied by PID {pid}. Freeing port...")
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        time.sleep(1)
        except Exception:
            pass

def open_browser():
    """Wait for server to bind then open default web browser."""
    for _ in range(30):
        if is_port_in_use(PORT, HOST):
            break
        time.sleep(0.3)
    time.sleep(0.5)
    print(f"\n[+] Opening MediConnect in your browser: {URL}")
    webbrowser.open(URL)

def main():
    print("=" * 68)
    print("       * MEDICONNECT — PREDICTIVE EHR FIELD COMPANION *")
    print("=" * 68)
    
    # 1. Dependency check
    check_and_install_dependencies()

    # 2. Database check & initialization
    try:
        from database import init_db
        init_db()
    except Exception as e:
        print(f"[!] Note on database init: {e}")

    # 3. Port check & cleanup
    free_port_if_needed(PORT)

    # 4. Print Login Credentials & Information
    print(f">> Web Application URL: {URL}")
    print(f">> Interactive API Docs: {URL}/docs")
    print("-" * 68)
    print("DEMO LOGIN CREDENTIALS:")
    print("  * ASHA Worker 1:   Username: asha_sunita  | Password: asha123  (Village: Rampur)")
    print("  * ASHA Worker 2:   Username: asha_anita   | Password: asha123  (Village: Bhimpur)")
    print("  * ANM Supervisor:  Username: admin_meena  | Password: admin123 (Block PHC)")
    print("-" * 68)
    print("Features ready:")
    print("  [x] Full Offline & Sync Gateway (intermittent field connection)")
    print("  [x] ML Maternal Health Risk Prediction & Referral Engine")
    print("  [x] Child Universal Immunization Programme (UIP) 12-Dose Tracking")
    print("  [x] Interactive Child Schedule View, Preview & Dose Recording")
    print("  [x] Village Outbreak Early Warning Anomaly Surveillance")
    print("  [x] 1-Click Fresh Start / Clean Database Reset")
    print("=" * 68)
    print("Press CTRL+C anytime in this window to stop the server.\n")

    # 5. Launch browser in background thread
    threading.Thread(target=open_browser, daemon=True).start()

    # 6. Run Uvicorn server
    import uvicorn
    from main import app
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")

if __name__ == "__main__":
    main()
