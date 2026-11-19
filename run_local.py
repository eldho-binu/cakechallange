"""
Local Development Runner for Christmas Cake Challenge
Runs both the Flask API Backend (port 5000) and Frontend Server (port 3000) concurrently.
"""
import os
import sys
import time
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# Add backend directory to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

def run_backend():
    from api.index import app
    print("🎄 Starting Flask Backend API on http://localhost:5000 ...")
    # Suppress verbose werkzeug logs in console
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

class CustomFrontendHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def end_headers(self):
        # Enable CORS headers and no-cache for development
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def log_message(self, format, *args):
        # Quiet logger
        pass

def run_frontend():
    print("🎂 Starting Frontend Web Server on http://localhost:3000 ...")
    server = ThreadingHTTPServer(("0.0.0.0", 3000), CustomFrontendHandler)
    server.serve_forever()

if __name__ == "__main__":
    t_backend = threading.Thread(target=run_backend, daemon=True)
    t_frontend = threading.Thread(target=run_frontend, daemon=True)

    t_backend.start()
    time.sleep(1)
    t_frontend.start()

    print("\n" + "=" * 65)
    print("⭐ CHRISTMAS CAKE CHALLENGE IS RUNNING LOCALLY! ⭐")
    print("=" * 65)
    print("🌐 Frontend App URL:     http://localhost:3000")
    print("👤 Member Login:        http://localhost:3000/login.html")
    print("✨ Request Access:       http://localhost:3000/login.html?tab=request")
    print("🛡️ Admin Portal:         http://localhost:3000/login.html?tab=admin")
    print("🔌 Backend API Health:   http://localhost:5000/api/system/status")
    print("-" * 65)
    print("Master Admin Email:     margregoriousyouthpancode123@gmail.com")
    print("Default Admin Password: Admin@Christmas2026!")
    print("=" * 65 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping servers... Goodbye!")
        sys.exit(0)
