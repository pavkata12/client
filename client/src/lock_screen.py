from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QFont
import os
import json
import keyboard
from network_manager import NetworkManager
import sys
import subprocess
from datetime import datetime, timedelta

class LockScreen(QWidget):
    """A fullscreen black lock screen with connection UI and session logic."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.setup_window_properties()
        self.connection_timer = QTimer(self)
        self.connection_timer.timeout.connect(self.try_reconnect)
        self.server_ip = None
        self.server_port = None
        self.connected = False
        self.network = NetworkManager()
        self.session_active = False
        self.timer_process = None
        self.timer_update_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'timer_update.json')
        self.pause_time = None
        self.remaining_time_at_pause = None
        self.session_end_time = None
        self.paused = False
        self.load_server_config()
        self.register_handlers()
        # Add timer to check if timer UI has exited
        self.timer_check = QTimer(self)
        self.timer_check.timeout.connect(self.check_timer_process)
        self.timer_check.start(2000)
        if self.server_ip and self.server_port:
            self.set_connection_ui_visible(False)
            self.status_label.setText("Connecting to server...")
            self.try_connect_and_start_timer()
        else:
            self.set_connection_ui_visible(True)
        
    def register_handlers(self):
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
        session_id = message['session_id']
        duration = message['duration']
        self.session_active = True
        self.paused = False
        self.pause_time = None
        self.remaining_time_at_pause = None
        self.session_end_time = datetime.now() + timedelta(hours=duration)
        self.launch_timer_ui(self.session_end_time)
        self.status_label.setText(f"Session {session_id} started for {duration} hours")

    def handle_end_session(self, message):
        self.session_active = False
        self.paused = False
        self.pause_time = None
        self.remaining_time_at_pause = None
        self.session_end_time = None
        self.close_timer_ui()
        self.status_label.setText("Session ended")

    def handle_extend_session(self, message):
        minutes = message.get('minutes', 0)
        if self.session_active:
            if self.paused and self.remaining_time_at_pause:
                self.remaining_time_at_pause += timedelta(minutes=minutes)
            elif self.session_end_time:
                self.session_end_time += timedelta(minutes=minutes)
                # Update the timer UI via a file if running
                if self.timer_process and self.timer_process.poll() is None:
                    with open(self.timer_update_file, 'w') as f:
                        json.dump({'end_time': self.session_end_time.isoformat()}, f)
            self.status_label.setText(f"Session extended by {minutes} minutes")

    def handle_pause_session(self, message):
        if self.session_active and not self.paused:
            self.paused = True
            self.pause_time = datetime.now()
            if self.session_end_time:
                self.remaining_time_at_pause = self.session_end_time - self.pause_time
            self.close_timer_ui()
            self.status_label.setText(f"Session paused at: {self.pause_time.strftime('%Y-%m-%d %H:%M:%S')}")

    def handle_resume_session(self, message):
        if self.session_active and self.paused and self.remaining_time_at_pause:
            self.paused = False
            new_end_time = datetime.now() + self.remaining_time_at_pause
            self.session_end_time = new_end_time
            self.launch_timer_ui(self.session_end_time)
            self.status_label.setText("Session resumed")
            self.pause_time = None
            self.remaining_time_at_pause = None

    def handle_lock_computer(self, message):
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        self.status_label.setText("Computer locked by admin")

    def handle_shutdown_computer(self, message):
        os.system("shutdown /s /t 1")

    def handle_maintenance_mode(self, message):
        QMessageBox.information(self, "Maintenance Mode", "This computer is now in maintenance mode. Please contact staff.")
        self.setEnabled(False)

    def handle_computer_removed(self, message):
        QMessageBox.information(self, "Computer Removed", "This computer has been removed from the system. The application will now close.")
        QApplication.quit()

    def handle_connection_lost(self, message):
        self.status_label.setText("Connection lost - attempting to reconnect...")
        if self.session_active:
            self.close_timer_ui()

    def launch_timer_ui(self, end_time):
        self.hide()  # Hide lock screen
        main_py = os.path.join(os.path.dirname(__file__), 'main.py')
        python_exe = sys.executable
        end_time_str = end_time.isoformat()
        # Write initial end_time to the update file
        with open(self.timer_update_file, 'w') as f:
            json.dump({'end_time': end_time_str}, f)
        self.timer_process = subprocess.Popen([python_exe, main_py, end_time_str])

    def close_timer_ui(self):
        if self.timer_process and self.timer_process.poll() is None:
            self.timer_process.terminate()
            self.timer_process = None
        self.showFullScreen()  # Show lock screen again
        self.activateWindow()

    def setup_window_properties(self):
        """Configure window properties for lock screen."""
        # Make window fullscreen and always on top, not minimizable
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.CustomizeWindowHint  # disables minimize/maximize/close buttons
        )
        # Set black background
        self.setStyleSheet("""
            QWidget {
                background-color: black;
                color: white;
            }
            QLabel {
                color: white;
                font-size: 14px;
            }
            QLineEdit {
                background-color: #333;
                color: white;
                border: 1px solid #555;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton {
                background-color: #444;
                color: white;
                border: 1px solid #666;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #555;
            }
        """)
        
    def setup_ui(self):
        """Setup the lock screen UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(50, 50, 50, 50)
        
        # Title
        title = QLabel("Gaming Center Client")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Status
        self.status_label = QLabel("Status: Disconnected")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Countdown label for reconnect
        self.countdown_label = QLabel("")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        countdown_font = QFont()
        countdown_font.setPointSize(18)
        countdown_font.setBold(True)
        self.countdown_label.setFont(countdown_font)
        layout.addWidget(self.countdown_label)
        
        # Server connection controls
        server_layout = QHBoxLayout()
        
        # IP input
        ip_layout = QVBoxLayout()
        self.ip_label = QLabel("Server IP:")
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("Enter server IP")
        ip_layout.addWidget(self.ip_label)
        ip_layout.addWidget(self.ip_input)
        server_layout.addLayout(ip_layout)
        
        # Port input
        port_layout = QVBoxLayout()
        self.port_label = QLabel("Port:")
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("Enter port")
        self.port_input.setText("5000")  # Default port
        port_layout.addWidget(self.port_label)
        port_layout.addWidget(self.port_input)
        server_layout.addLayout(port_layout)
        
        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.handle_connect)
        server_layout.addWidget(self.connect_btn)
        
        layout.addLayout(server_layout)
        
        # Add some spacing
        layout.addStretch()
        
    def set_connection_ui_visible(self, visible):
        self.ip_input.setVisible(visible)
        self.port_input.setVisible(visible)
        self.connect_btn.setVisible(visible)
        self.ip_label.setVisible(visible)
        self.port_label.setVisible(visible)

    def load_server_config(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'client_config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.server_ip = config.get('server_ip')
                    self.server_port = config.get('server_port')
            except Exception:
                self.server_ip = None
                self.server_port = None
        else:
            self.server_ip = None
            self.server_port = None

    def save_server_config(self, ip, port):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'client_config.json')
        try:
            with open(config_path, 'w') as f:
                json.dump({'server_ip': ip, 'server_port': port}, f)
        except Exception:
            pass

    def try_connect_and_start_timer(self):
        if self.network.connect(self.server_ip, self.server_port):
            self.connected = True
            self.status_label.setText("Connected to server")
        else:
            self.connected = False
            self.connection_timer.start(5000)
            self.status_label.setText("Failed to connect. Retrying...")
            self.start_reconnect_countdown(5)

    def handle_connect(self):
        """Handle connect button click."""
        try:
            ip = self.ip_input.text().strip()
            port = int(self.port_input.text().strip())
            if not ip:
                QMessageBox.warning(self, "Error", "Please enter a server IP address")
                return
            self.save_server_config(ip, port)
            self.server_ip = ip
            self.server_port = port
            self.set_connection_ui_visible(False)
            self.status_label.setText("Connecting to server...")
            self.try_connect_and_start_timer()
        except ValueError:
            QMessageBox.warning(self, "Error", "Please enter a valid port number")
            
    def start_reconnect_countdown(self, seconds=5):
        self._reconnect_seconds = seconds
        self.countdown_label.setText(f"Reconnecting in {self._reconnect_seconds}...")
        if not hasattr(self, '_countdown_timer'):
            self._countdown_timer = QTimer(self)
            self._countdown_timer.timeout.connect(self._update_reconnect_countdown)
        self._countdown_timer.start(1000)

    def _update_reconnect_countdown(self):
        self._reconnect_seconds -= 1
        if self._reconnect_seconds > 0:
            self.countdown_label.setText(f"Reconnecting in {self._reconnect_seconds}...")
        else:
            self.countdown_label.setText("")
            self._countdown_timer.stop()

    def try_reconnect(self):
        if not self.connected and self.server_ip and self.server_port:
            self.status_label.setText("Connecting to server...")
            if self.network.connect(self.server_ip, self.server_port):
                self.connected = True
                self.connection_timer.stop()
                self.status_label.setText("Connected to server")
            else:
                self.connected = False
                self.status_label.setText("Failed to connect. Retrying...")
                self.start_reconnect_countdown(5)

    def update_status(self, status):
        """Update the status label."""
        self.status_label.setText(f"Status: {status}")
        if status == "Connected to server":
            self.connected = True
            self.connection_timer.stop()
            self.countdown_label.setText("")
        else:
            self.connected = False
            if self.server_ip and self.server_port:
                if not self.connection_timer.isActive():
                    self.connection_timer.start(5000)  # Try to reconnect every 5 seconds
                    self.status_label.setText("Connection lost - attempting to reconnect...")
                    self.start_reconnect_countdown(5)
        
    def showEvent(self, event):
        """Handle show event to ensure window is fullscreen."""
        super().showEvent(event)
        self.showFullScreen()
        # Block Windows keys when lock screen is shown
        keyboard.block_key('left windows')
        keyboard.block_key('right windows')

    def hideEvent(self, event):
        super().hideEvent(event)
        # Unblock Windows keys when lock screen is hidden
        keyboard.unblock_key('left windows')
        keyboard.unblock_key('right windows')

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if self.windowState() & Qt.WindowMinimized:
                self.showNormal()
                self.activateWindow()
        super().changeEvent(event)

    def show_pause_message(self, pause_time_str):
        self.set_connection_ui_visible(False)
        self.status_label.setText(f"Session paused at: {pause_time_str}")

    def check_timer_process(self):
        if self.timer_process and self.timer_process.poll() is not None:
            self.timer_process = None
            self.showFullScreen()
            self.activateWindow()

def main():
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    lock_screen = LockScreen()
    lock_screen.showFullScreen()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 