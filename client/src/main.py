import sys
import os
import json
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QMessageBox, QGroupBox, QListWidget, QListWidgetItem, QInputDialog, QSystemTrayIcon, QMenu
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QObject, QEvent
from PySide6.QtGui import QIcon, QFont, QAction
import time
import logging
from zeroconf import Zeroconf, ServiceBrowser
import win32gui, win32con
import subprocess

# Add the src directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from network_manager import NetworkManager
from config import (
    WINDOW_TITLE, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
    DEFAULT_SERVER_IP, DEFAULT_SERVER_PORT,
    DATETIME_FORMAT
)
from lock_screen import LockScreen

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StatusUpdater(QObject):
    status_changed = Signal(str)
    session_started = Signal(int, int)  # session_id, duration
    session_ended = Signal(bool)  # force_end
    session_extended = Signal(int)  # minutes

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
        self.zeroconf = Zeroconf()
        self.discovery_browser = None
        
        # Create lock screen
        self.lock_screen = LockScreen()
        self.lock_screen.connect_requested.connect(
            lambda ip, port: self.connect_to_server(ip, port)
        )
        
        # Connect signals
        self.status_updater.status_changed.connect(self.update_status_label)
        self.status_updater.session_started.connect(self.start_session)
        self.status_updater.session_ended.connect(self.end_session)
        self.status_updater.session_extended.connect(self.on_session_extended)
        
        # Robust tray icon path
        icon_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'icon.png')
        if not os.path.exists(icon_path):
            # Use a default Qt icon if missing
            self.tray_icon = QSystemTrayIcon(self.style().standardIcon(QStyle.SP_ComputerIcon), self)
        else:
            self.tray_icon = QSystemTrayIcon(QIcon(icon_path), self)
        tray_menu = QMenu()
        restore_action = QAction("Restore", self)
        restore_action.triggered.connect(self.show_normal_from_tray)
        tray_menu.addAction(restore_action)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.quit)
        tray_menu.addAction(exit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        
        self.setup_ui()
        self.setup_network_handlers()
        self.load_server_config()

        # Add a QTimer to update the session timer every second
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)

        self.focus_timer = QTimer(self)
        self.focus_timer.timeout.connect(self.enforce_window_focus)
        
        # Show lock screen on startup
        self.lock_screen.show()
        self.hide()

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
                end_time = self.current_session.get('end_time')
                if not end_time or not isinstance(end_time, datetime):
                    self.current_session['end_time'] = datetime.now() + timedelta(minutes=minutes)
                else:
                    self.current_session['end_time'] += timedelta(minutes=minutes)
                logger.info(f"Session extended by {minutes} minutes.")
                self.status_updater.session_extended.emit(minutes)
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
        QApplication.quit()

    def handle_connection_lost(self, message):
        """Handle connection lost message."""
        self.status_label.setText("Connection lost - attempting to reconnect...")
        QTimer.singleShot(5000, self.reconnect_to_server)

    def update_status_label(self, status):
        """Update the status label in the UI thread."""
        self.status_label.setText(status)
        self.lock_screen.update_status(status)

    def apply_gothic_style(self):
        gothic_qss = """
        QMainWindow, QWidget {
            background-color: #18141a;
            color: #fff;
        }
        QLabel, QLineEdit, QTableWidget, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QGroupBox {
            color: #fff;
        }
        QTabBar::tab {
            background: #2d223a;
            color: #fff;
            border: 1px solid #3a2a4d;
            border-radius: 6px 6px 0 0;
            padding: 8px 20px;
            font-weight: bold;
        }
        QTabBar::tab:selected {
            background: #4b2e5c;
            color: #fff;
        }
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3a2a4d, stop:1 #18141a);
            color: #fff;
            border: 1px solid #6c4e7c;
            border-radius: 6px;
            padding: 6px 16px;
            font-weight: bold;
        }
        QPushButton:hover {
            background: #4b2e5c;
            color: #fff;
            border: 1px solid #a084ca;
        }
        QLabel#headingLabel {
            font-family: 'UnifrakturCook', 'Old English Text MT', 'Segoe UI', serif;
            font-size: 24px;
            color: #fff;
            font-weight: bold;
        }
        QHeaderView::section {
            background: #2d223a;
            color: #fff;
            border: 1px solid #3a2a4d;
            font-weight: bold;
        }
        """
        self.setStyleSheet(gothic_qss)

    def setup_ui(self):
        self.apply_gothic_style()
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        # Add a gothic heading label at the top
        heading = QLabel("Gaming Center Client")
        heading.setObjectName("headingLabel")
        heading.setAlignment(Qt.AlignCenter)
        font = heading.font()
        font.setPointSize(24)
        font.setBold(True)
        heading.setFont(font)
        layout.insertWidget(0, heading)
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
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.time_label)
        layout.addWidget(status_group)

    def discover_server(self):
        def on_found(ip, port):
            self.server_ip_input.setText(ip)
            self.server_port_input.setText(str(port))
            QMessageBox.information(self, "Server Found", f"Discovered server at {ip}:{port}")
            if self.discovery_browser:
                self.discovery_browser.cancel()
        self.discovery_browser = ServiceBrowser(self.zeroconf, "_gamingcenter._tcp.local.", ServerDiscoveryListener(on_found))

    def connect_to_server(self, ip=None, port=None):
        """Connect to the server and save the IP/port to config.json if successful."""
        try:
            # Use values from lock screen if provided, else from main UI
            server_ip = ip or self.server_ip_input.text()
            server_port = int(port or self.server_port_input.text())
            if self.network.connect(server_ip, server_port):
                self.status_updater.status_changed.emit("Connected to server")
                self.save_server_config(server_ip, server_port)
            else:
                self.status_updater.status_changed.emit("Failed to connect to server")
        except Exception as e:
            logger.error(f"Error connecting to server: {e}")
            self.status_updater.status_changed.emit("Error connecting to server")

    def save_server_config(self, ip, port):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'client_config.json')
        try:
            with open(config_path, 'w') as f:
                json.dump({'server_ip': ip, 'server_port': port}, f)
            # Update both UIs
            self.server_ip_input.setText(ip)
            self.server_port_input.setText(str(port))
            self.lock_screen.ip_input.setText(ip)
            self.lock_screen.port_input.setText(str(port))
        except Exception as e:
            logger.error(f"Error saving server config: {e}")

    def load_server_config(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'client_config.json')
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    ip = config.get('server_ip', '')
                    port = str(config.get('server_port', DEFAULT_SERVER_PORT))
                    self.server_ip_input.setText(ip)
                    self.server_port_input.setText(port)
                    self.lock_screen.ip_input.setText(ip)
                    self.lock_screen.port_input.setText(port)
        except Exception as e:
            logger.error(f"Error loading server config: {e}")

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
            self.status_label.setText(f"Session {session_id} active")
            self.time_label.setText(f"Duration: {duration} hours")
            logger.info(f"Session {session_id} started successfully")
            # Hide lock screen and show main window
            self.lock_screen.hide()
            self.lock_screen.setWindowState(Qt.WindowNoState)
            self.show()
            self.raise_()
            self.activateWindow()
            # Minimize to tray after 1 second
            QTimer.singleShot(1000, self.minimize_to_tray)
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
                self.status_label.setText("No active session")
                self.time_label.setText("")
                logger.info("Session ended")
                # Relaunch lock screen and close main UI
                self.hide()
                lock_screen_py = os.path.join(os.path.dirname(__file__), 'lock_screen_main.py')
                python_exe = sys.executable
                subprocess.Popen([python_exe, lock_screen_py])
                QApplication.quit()
                if force_end:
                    QMessageBox.information(self, "Session Ended", "Your session has been ended by the administrator.")

    def closeEvent(self, event):
            super().closeEvent(event)

    def enforce_window_focus(self):
        hwnd = win32gui.FindWindow(None, self.windowTitle())
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                self.tray_icon.show()
                self.hide()
        super().changeEvent(event)

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key_U and
            event.modifiers() & Qt.ControlModifier and
            event.modifiers() & Qt.AltModifier and
            event.modifiers() & Qt.ShiftModifier):
            if self.prompt_admin_password():
                QMessageBox.information(self, "Admin Access", "Admin access granted.")
        super().keyPressEvent(event)

    def prompt_admin_password(self):
        password, ok = QInputDialog.getText(self, "Admin Unlock", "Enter admin password:", QLineEdit.Password)
        return ok and password == "your_admin_password"

    def show_normal_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.tray_icon.hide()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_normal_from_tray()

    def minimize_to_tray(self):
        self.tray_icon.show()
        self.hide()

    def on_session_extended(self, minutes):
        QMessageBox.information(self, "Session Extended", f"Your session has been extended by {minutes} minutes.")

def main():
    app = QApplication(sys.argv)
    window = GamingCenterClient()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 