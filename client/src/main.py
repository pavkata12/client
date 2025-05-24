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
from zeroconf import Zeroconf, ServiceBrowser

# Add the src directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from network_manager import NetworkManager
from system_locker import SystemLocker
from config import (
    WINDOW_TITLE, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
    DEFAULT_SERVER_IP, DEFAULT_SERVER_PORT,
    DATETIME_FORMAT
)
from kiosk_controller import KioskController

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StatusUpdater(QObject):
    status_changed = Signal(str)
    session_started = Signal(int, int)  # session_id, duration
    session_ended = Signal(bool)  # force_end

class ServerDiscoveryListener:
    def __init__(self, callback):
        self.callback = callback
    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info:
            ip = '.'.join(str(b) for b in info.addresses[0])
            port = info.port
            self.callback(ip, port)

class GamingCenterClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.network = NetworkManager()
        self.current_session = None
        self.status_updater = StatusUpdater()
        self.kiosk_controller = KioskController()
        self.zeroconf = Zeroconf()
        self.discovery_browser = None
        
        # Connect signals
        self.status_updater.status_changed.connect(self.update_status_label)
        self.status_updater.session_started.connect(self.start_session)
        self.status_updater.session_ended.connect(self.end_session)
        self.kiosk_controller.process_blocked.connect(self.on_process_blocked)
        self.kiosk_controller.kiosk_status_changed.connect(self.on_kiosk_status_changed)
        self.kiosk_controller.admin_required.connect(self.show_admin_warning)
        
        self.setup_ui()
        self.setup_network_handlers()
        self.setup_kiosk()

        # Admin privilege check
        if not self.kiosk_controller.is_admin:
            self.show_admin_warning()

    def setup_network_handlers(self):
        """Setup network message handlers."""
        self.network.register_handler("start_session", self.handle_start_session)
        self.network.register_handler("end_session", self.handle_end_session)
        self.network.register_handler("extend_session", self.handle_extend_session)
        self.network.register_handler("pause_session", self.handle_pause_session)
        self.network.register_handler("resume_session", self.handle_resume_session)
        self.network.register_handler("lock_computer", self.handle_lock_computer)
        self.network.register_handler("shutdown_computer", self.handle_shutdown_computer)
        self.network.register_handler("maintenance_mode", self.handle_maintenance_mode)
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

    def handle_extend_session(self, message):
        """Handle session extension from server."""
        try:
            minutes = message.get('minutes', 0)
            if self.current_session:
                self.current_session['end_time'] += timedelta(minutes=minutes)
                logger.info(f"Session extended by {minutes} minutes.")
                QMessageBox.information(self, "Session Extended", f"Your session has been extended by {minutes} minutes.")
        except Exception as e:
            logger.error(f"Error handling extend session: {e}")

    def handle_pause_session(self, message):
        """Handle session pause from server."""
        if self.current_session:
            self.session_paused = True
            self.status_label.setText("Session Paused")
            QMessageBox.information(self, "Session Paused", "Your session has been paused by the administrator.")

    def handle_resume_session(self, message):
        """Handle session resume from server."""
        if self.current_session:
            self.session_paused = False
            self.status_label.setText("Session Active")
            QMessageBox.information(self, "Session Resumed", "Your session has been resumed by the administrator.")

    def handle_lock_computer(self, message):
        """Handle remote lock command from server."""
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            QMessageBox.information(self, "Locked", "This computer has been locked by the administrator.")
        except Exception as e:
            logger.error(f"Error locking workstation: {e}")

    def handle_shutdown_computer(self, message):
        """Handle remote shutdown command from server."""
        try:
            os.system("shutdown /s /t 1")
        except Exception as e:
            logger.error(f"Error shutting down: {e}")

    def handle_maintenance_mode(self, message):
        """Handle remote maintenance mode command from server."""
        QMessageBox.information(self, "Maintenance Mode", "This computer is now in maintenance mode. Please contact staff.")
        self.setEnabled(False)

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

        # Server connection controls
        server_layout = QHBoxLayout()
        self.server_ip_input = QLineEdit()
        self.server_ip_input.setPlaceholderText("Server IP Address")
        self.server_port_input = QLineEdit()
        self.server_port_input.setPlaceholderText("Server Port")
        self.server_port_input.setText(str(DEFAULT_SERVER_PORT))
        discover_btn = QPushButton("Discover Server")
        discover_btn.clicked.connect(self.discover_server)
        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self.connect_to_server)
        server_layout.addWidget(QLabel("Server IP:"))
        server_layout.addWidget(self.server_ip_input)
        server_layout.addWidget(QLabel("Port:"))
        server_layout.addWidget(self.server_port_input)
        server_layout.addWidget(discover_btn)
        server_layout.addWidget(connect_btn)
        layout.addLayout(server_layout)

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
        for app_name, app_info in self.kiosk_controller.get_allowed_apps().items():
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
        config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'allowed_apps.json')
        self.kiosk_controller.load_allowed_apps(config_path)

    def toggle_kiosk_mode(self):
        """Toggle kiosk mode on/off."""
        if not self.kiosk_controller.is_kiosk_mode:
            self.kiosk_controller.start_kiosk_mode()
            self.kiosk_toggle_btn.setText("Disable Kiosk Mode")
        else:
            self.kiosk_controller.stop_kiosk_mode()
            self.kiosk_toggle_btn.setText("Enable Kiosk Mode")

    def launch_application(self, item):
        """Launch the selected application."""
        app_name = item.data(Qt.UserRole)
        if self.kiosk_controller.launch_allowed_app(app_name):
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

    def show_admin_warning(self):
        QMessageBox.warning(self, "Administrator Required", "This application must be run as administrator for kiosk mode and security features to work correctly.")

    def discover_server(self):
        def on_found(ip, port):
            self.server_ip_input.setText(ip)
            self.server_port_input.setText(str(port))
            QMessageBox.information(self, "Server Found", f"Discovered server at {ip}:{port}")
            if self.discovery_browser:
                self.discovery_browser.cancel()
        self.discovery_browser = ServiceBrowser(self.zeroconf, "_gamingcenter._tcp.local.", ServerDiscoveryListener(on_found))

    def connect_to_server(self):
        """Connect to the server."""
        try:
            server_ip = self.server_ip_input.text()
            server_port = int(self.server_port_input.text())
            
            if self.network.connect(server_ip, server_port):
                self.status_updater.status_changed.emit("Connected to server")
            else:
                self.status_updater.status_changed.emit("Failed to connect to server")
        except Exception as e:
            logger.error(f"Error connecting to server: {e}")
            self.status_updater.status_changed.emit("Error connecting to server")

    def update_status(self):
        """Update the status display."""
        if self.current_session:
            if getattr(self, 'session_paused', False):
                self.time_label.setText("Session paused")
                return
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
        elif self.kiosk_controller.is_kiosk_mode:
            self.kiosk_controller.stop_kiosk_mode()
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