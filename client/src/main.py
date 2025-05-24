import sys
import os
import json
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QMessageBox, QGroupBox, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QObject
from PySide6.QtGui import QIcon, QFont
import time
import logging

# Add the src directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from network_manager import NetworkManager
from system_locker import SystemLocker
from config import (
    WINDOW_TITLE, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
    DEFAULT_SERVER_IP, DEFAULT_SERVER_PORT,
    DATETIME_FORMAT
)
from kiosk_manager import KioskManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StatusUpdater(QObject):
    status_changed = Signal(str)
    session_started = Signal(int, int)  # session_id, duration
    session_ended = Signal(bool)  # force_end

class GamingCenterClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.network = NetworkManager()
        self.system_locker = SystemLocker()
        self.current_session = None
        self.status_updater = StatusUpdater()
        self.kiosk_manager = KioskManager()
        
        # Connect signals
        self.status_updater.status_changed.connect(self.update_status_label)
        self.status_updater.session_started.connect(self.start_session)
        self.status_updater.session_ended.connect(self.end_session)
        self.kiosk_manager.process_blocked.connect(self.on_process_blocked)
        self.kiosk_manager.kiosk_status_changed.connect(self.on_kiosk_status_changed)
        
        self.setup_ui()
        self.load_config()
        self.setup_network_handlers()
        self.connect_to_server()
        self.setup_kiosk()

    def setup_network_handlers(self):
        """Setup network message handlers."""
        self.network.register_handler("start_session", self.handle_start_session)
        self.network.register_handler("end_session", self.handle_end_session)
        self.network.register_handler("computer_removed", self.handle_computer_removed)
        self.network.register_handler("connection_lost", self.handle_connection_lost)

    def handle_start_session(self, message):
        """Handle session start message from server."""
        try:
            session_id = message['session_id']
            duration = message['duration']
            logger.info(f"Starting session {session_id} for {duration} hours")
            self.status_updater.session_started.emit(session_id, duration)
        except Exception as e:
            logger.error(f"Error handling start session: {e}")

    def handle_end_session(self, message):
        """Handle session end message from server."""
        try:
            force_end = message.get('force_end', False)
            logger.info(f"Ending session (force: {force_end})")
            self.status_updater.session_ended.emit(force_end)
        except Exception as e:
            logger.error(f"Error handling end session: {e}")

    def handle_computer_removed(self, message):
        """Handle computer removed message from server."""
        QMessageBox.information(self, "Computer Removed", "This computer has been removed from the system. The application will now close.")
        self.close()

    def handle_connection_lost(self, message):
        """Handle connection lost message."""
        self.status_label.setText("Connection lost - attempting to reconnect...")
        QTimer.singleShot(5000, self.reconnect_to_server)

    def reconnect_to_server(self):
        """Attempt to reconnect to the server."""
        if not self.network.is_connected():
            self.connect_to_server()

    def update_status_label(self, status):
        """Update the status label in the UI thread."""
        self.status_label.setText(status)

    def setup_ui(self):
        """Setup the main window UI."""
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Status section
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        
        self.status_label = QLabel("Status: Disconnected")
        self.time_label = QLabel("Time Remaining: --:--")
        self.kiosk_status_label = QLabel("Kiosk Mode: Disabled")
        
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.time_label)
        status_layout.addWidget(self.kiosk_status_label)
        layout.addWidget(status_group)

        # Applications section
        apps_group = QGroupBox("Applications")
        apps_layout = QVBoxLayout(apps_group)
        
        self.apps_list = QListWidget()
        self.apps_list.itemDoubleClicked.connect(self.launch_application)
        apps_layout.addWidget(self.apps_list)
        
        # Add applications to the list
        for app_name, app_info in self.kiosk_manager.get_allowed_apps().items():
            item = QListWidgetItem(app_info['window_title'])
            item.setData(Qt.UserRole, app_name)
            self.apps_list.addItem(item)
        
        layout.addWidget(apps_group)

        # Control buttons
        button_layout = QHBoxLayout()
        
        self.kiosk_toggle_btn = QPushButton("Enable Kiosk Mode")
        self.kiosk_toggle_btn.clicked.connect(self.toggle_kiosk_mode)
        button_layout.addWidget(self.kiosk_toggle_btn)
        
        layout.addLayout(button_layout)

    def setup_kiosk(self):
        """Setup kiosk mode manager."""
        self.kiosk_manager = KioskManager()
        self.kiosk_manager.process_blocked.connect(self.on_process_blocked)
        self.kiosk_manager.kiosk_status_changed.connect(self.on_kiosk_status_changed)
        
        # Load allowed applications configuration
        config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'allowed_apps.json')
        self.kiosk_manager.load_allowed_apps(config_path)

    def toggle_kiosk_mode(self):
        """Toggle kiosk mode on/off."""
        if not self.kiosk_manager.is_kiosk_mode:
            self.kiosk_manager.start_kiosk_mode()
            self.kiosk_toggle_btn.setText("Disable Kiosk Mode")
        else:
            self.kiosk_manager.stop_kiosk_mode()
            self.kiosk_toggle_btn.setText("Enable Kiosk Mode")

    def launch_application(self, item):
        """Launch the selected application."""
        app_name = item.data(Qt.UserRole)
        if self.kiosk_manager.launch_allowed_app(app_name):
            logger.info(f"Launched {app_name}")
        else:
            QMessageBox.warning(self, "Error", f"Failed to launch {app_name}")

    def on_process_blocked(self, process_name):
        """Handle blocked process event."""
        logger.info(f"Blocked unauthorized process: {process_name}")

    def on_kiosk_status_changed(self, enabled):
        """Handle kiosk mode status change."""
        self.kiosk_status_label.setText(f"Kiosk Mode: {'Enabled' if enabled else 'Disabled'}")
        if enabled:
            self.kiosk_toggle_btn.setText("Disable Kiosk Mode")
        else:
            self.kiosk_toggle_btn.setText("Enable Kiosk Mode")

    def load_config(self):
        """Load configuration from file."""
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.server_ip_input.setText(config.get('server_ip', DEFAULT_SERVER_IP))
                    self.server_port_input.setText(str(config.get('server_port', DEFAULT_SERVER_PORT)))
            else:
                self.server_ip_input.setText(DEFAULT_SERVER_IP)
                self.server_port_input.setText(str(DEFAULT_SERVER_PORT))
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.server_ip_input.setText(DEFAULT_SERVER_IP)
            self.server_port_input.setText(str(DEFAULT_SERVER_PORT))

    def save_config(self):
        """Save configuration to file."""
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        try:
            config = {
                'server_ip': self.server_ip_input.text(),
                'server_port': int(self.server_port_input.text())
            }
            with open(config_path, 'w') as f:
                json.dump(config, f)
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def connect_to_server(self):
        """Connect to the server."""
        try:
            server_ip = self.server_ip_input.text()
            server_port = int(self.server_port_input.text())
            
            if self.network.connect(server_ip, server_port):
                self.status_updater.status_changed.emit("Connected to server")
                self.save_config()
            else:
                self.status_updater.status_changed.emit("Failed to connect to server")
        except Exception as e:
            logger.error(f"Error connecting to server: {e}")
            self.status_updater.status_changed.emit("Error connecting to server")

    def update_status(self):
        """Update the status display."""
        if self.current_session:
            remaining = self.current_session['end_time'] - datetime.now()
            if remaining.total_seconds() > 0:
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                seconds = int(remaining.total_seconds() % 60)
                self.time_label.setText(f"Time remaining: {hours:02d}:{minutes:02d}:{seconds:02d}")
            else:
                self.end_session()

    def start_session(self, session_id: int, duration: int):
        """Start a new session."""
        try:
            self.current_session = {
                'id': session_id,
                'start_time': datetime.now(),
                'end_time': datetime.now() + timedelta(hours=duration)
            }
            self.session_label.setText(f"Session {session_id} active")
            self.time_label.setText(f"Duration: {duration} hours")
            self.end_session_btn.setEnabled(True)
            self.system_locker.start_monitoring()
            logger.info(f"Session {session_id} started successfully")
        except Exception as e:
            logger.error(f"Error starting session: {e}")

    def end_session(self, force_end=False):
        """End the current session."""
        if self.current_session:
            try:
                duration = int((datetime.now() - self.current_session['start_time']).total_seconds() / 60)
                self.network.send_message({
                    'type': 'session_end',
                    'session_id': self.current_session['id'],
                    'duration': duration,
                    'amount': 0  # This will be calculated by the server
                })
            except Exception as e:
                logger.error(f"Error ending session: {e}")
            finally:
                self.current_session = None
                self.session_label.setText("No active session")
                self.time_label.setText("")
                self.end_session_btn.setEnabled(False)
                self.system_locker.stop_monitoring()
                logger.info("Session ended")
                if force_end:
                    QMessageBox.information(self, "Session Ended", "Your session has been ended by the administrator.")

    def closeEvent(self, event):
        """Handle window close event."""
        if self.current_session:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "There is an active session. Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.end_session()
                event.accept()
            else:
                event.ignore()
        elif self.kiosk_manager.is_kiosk_mode:
            self.kiosk_manager.stop_kiosk_mode()
            event.accept()
        else:
            event.accept()

def main():
    app = QApplication(sys.argv)
    window = GamingCenterClient()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 