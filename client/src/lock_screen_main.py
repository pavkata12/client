import sys
import os
import json
import logging
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from lock_screen import LockScreen

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('lock_screen.log'),
        logging.StreamHandler()
    ]
)

def load_config():
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading config: {e}")
        return {"server_url": "http://localhost:5000"}

def main():
    app = QApplication(sys.argv)
    config = load_config()
    lock_screen = LockScreen(config["server_url"])
    lock_screen.show()

    # Reconnection timer
    reconnect_timer = QTimer()
    reconnect_timer.setInterval(5000)  # 5 seconds

    def try_reconnect():
        if not lock_screen.is_connected():
            logging.info("Attempting to reconnect to server...")
            lock_screen.connect_to_server()

    reconnect_timer.timeout.connect(try_reconnect)
    reconnect_timer.start()

    sys.exit(app.exec())

if __name__ == "__main__":
    main() 