from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QMessageBox, QApplication,
    QProgressBar, QFrame
)
from PySide6.QtCore import Qt, QEvent, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QPalette, QColor
import os
import json
import keyboard
import logging
from datetime import datetime, timedelta
from network_manager import NetworkManager
import sys
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent / 'data' / 'logs' / 'lock_screen.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class SessionState:
    """State management for the lock screen session."""
    active: bool = False
    session_id: Optional[str] = None
    end_time: Optional[datetime] = None
    paused: bool = False
    pause_time: Optional[datetime] = None
    remaining_time: Optional[timedelta] = None
    timer_process: Optional[subprocess.Popen] = None

class LockScreen(QWidget):
    """Enhanced fullscreen lock screen with connection UI and session logic."""
    
    # Signals
    session_started = Signal(str, int)  # session_id, duration
    session_ended = Signal()
    session_paused = Signal()
    session_resumed = Signal()
    connection_status_changed = Signal(bool)  # is_connected
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = SessionState()
        self.setup_ui()
        self.setup_window_properties()
        self.setup_timers()
        self.setup_network()
        self.load_config()
        self.register_handlers()
        
        # Connect to server if config exists
        if self.server_ip and self.server_port:
            self.set_connection_ui_visible(False)
            self.status_label.setText("Connecting to server...")
            self.try_connect_and_start_timer()
        else:
            self.set_connection_ui_visible(True)

    def setup_ui(self):
        """Setup the lock screen UI with enhanced styling."""
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
        
        # Connection progress
        self.connection_progress = QProgressBar()
        self.connection_progress.setRange(0, 0)  # Indeterminate progress
        self.connection_progress.setVisible(False)
        layout.addWidget(self.connection_progress)
        
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
        
        # Apply styles
        self.setup_styles()

    def setup_styles(self):
        """Setup application-wide styles."""
        self.setStyleSheet("""
            QWidget {
                background-color: #2c3e50;
                color: #ecf0f1;
            }
            QLabel {
                color: #ecf0f1;
                font-size: 14px;
            }
            QLineEdit {
                background-color: #34495e;
                color: #ecf0f1;
                border: 1px solid #7f8c8d;
                padding: 5px;
                border-radius: 3px;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #2472a4;
            }
            QProgressBar {
                border: 2px solid #34495e;
                border-radius: 5px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 3px;
            }
        """)

    def setup_window_properties(self):
        """Configure window properties for lock screen."""
        try:
            # Make window fullscreen and always on top
            self.setWindowFlags(
                Qt.Window |
                Qt.FramelessWindowHint |
                Qt.WindowStaysOnTopHint |
                Qt.CustomizeWindowHint
            )
        except Exception as e:
            logger.error(f"Error setting up window properties: {e}")

    def setup_timers(self):
        """Setup timers for reconnection and status updates."""
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.try_connect_and_start_timer)
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)

    def setup_network(self):
        """Initialize network manager."""
        self.network = NetworkManager()
        self.network.connection_status_changed.connect(self.handle_connection_status)

    def register_handlers(self):
        """Register network event handlers."""
        handlers = {
            "start_session": self.handle_start_session,
            "end_session": self.handle_end_session,
            "extend_session": self.handle_extend_session,
            "pause_session": self.handle_pause_session,
            "resume_session": self.handle_resume_session,
            "lock_computer": self.handle_lock_computer,
            "shutdown_computer": self.handle_shutdown_computer,
            "maintenance_mode": self.handle_maintenance_mode,
            "computer_removed": self.handle_computer_removed,
            "connection_lost": self.handle_connection_lost,
            "allowed_apps_update": self.handle_allowed_apps_update
        }
        
        for event, handler in handlers.items():
            self.network.register_message_handler(event, handler)

    def handle_start_session(self, message: Dict[str, Any]):
        """Handle session start event."""
        try:
            session_id = message.get('session_id')
            duration = message.get('duration')
            
            if not session_id or not duration:
                logger.error("Invalid session data received")
                return
                
            self.state.active = True
            self.state.paused = False
            self.state.pause_time = None
            self.state.remaining_time = None
            self.state.session_id = session_id
            self.state.end_time = datetime.now() + timedelta(hours=duration)
            
            self.launch_timer_ui(self.state.end_time)
            self.status_label.setText(f"Session {session_id} started for {duration} hours")
            self.session_started.emit(session_id, duration)
            
            logger.info(f"Session {session_id} started for {duration} hours")
            
        except Exception as e:
            logger.error(f"Error handling start session: {e}")
            QMessageBox.critical(self, "Error", "Failed to start session")

    def handle_end_session(self, message: Dict[str, Any]):
        """Handle session end event."""
        try:
            if not self.state.active:
                return
                
            self.state.active = False
            self.state.session_id = None
            self.state.end_time = None
            self.state.paused = False
            self.state.pause_time = None
            self.state.remaining_time = None
            
            self.close_timer_ui()
            self.status_label.setText("Session ended")
            self.session_ended.emit()
            
            logger.info("Session ended")
            
        except Exception as e:
            logger.error(f"Error handling end session: {e}")
            QMessageBox.critical(self, "Error", "Failed to end session")

    def handle_extend_session(self, message: Dict[str, Any]):
        """Handle session extension event."""
        try:
            minutes = message.get('minutes', 0)
            
            if not minutes or not self.state.active:
                return
                
            if self.state.end_time:
                self.state.end_time += timedelta(minutes=minutes)
                self.status_label.setText(f"Session extended by {minutes} minutes")
                
            logger.info(f"Session extended by {minutes} minutes")
            
        except Exception as e:
            logger.error(f"Error handling extend session: {e}")
            QMessageBox.critical(self, "Error", "Failed to extend session")

    def handle_pause_session(self, message: Dict[str, Any]):
        """Handle session pause event."""
        try:
            if not self.state.active or self.state.paused:
                return
                
            self.state.paused = True
            self.state.pause_time = datetime.now()
            
            if self.state.end_time:
                self.state.remaining_time = self.state.end_time - self.state.pause_time
                
            self.status_label.setText("Session paused")
            self.session_paused.emit()
            
            logger.info("Session paused")
            
        except Exception as e:
            logger.error(f"Error handling pause session: {e}")
            QMessageBox.critical(self, "Error", "Failed to pause session")

    def handle_resume_session(self, message: Dict[str, Any]):
        """Handle session resume event."""
        try:
            if not self.state.active or not self.state.paused:
                return
                
            self.state.paused = False
            self.state.pause_time = None
            
            if self.state.remaining_time:
                self.state.end_time = datetime.now() + self.state.remaining_time
                self.state.remaining_time = None
                
            self.status_label.setText("Session resumed")
            self.session_resumed.emit()
            
            logger.info("Session resumed")
            
        except Exception as e:
            logger.error(f"Error handling resume session: {e}")
            QMessageBox.critical(self, "Error", "Failed to resume session")

    def handle_lock_computer(self, message: Dict[str, Any]):
        """Handle computer lock event."""
        try:
            if sys.platform == 'win32':
                os.system('rundll32.exe user32.dll,LockWorkStation')
            logger.info("Computer locked")
            
        except Exception as e:
            logger.error(f"Error locking computer: {e}")
            QMessageBox.critical(self, "Error", "Failed to lock computer")

    def handle_shutdown_computer(self, message: Dict[str, Any]):
        """Handle computer shutdown event."""
        try:
            if sys.platform == 'win32':
                os.system('shutdown /s /t 0')
            logger.info("Computer shutdown initiated")
            
        except Exception as e:
            logger.error(f"Error shutting down computer: {e}")
            QMessageBox.critical(self, "Error", "Failed to shutdown computer")

    def handle_maintenance_mode(self, message: Dict[str, Any]):
        """Handle maintenance mode event."""
        try:
            self.handle_end_session(message)
            self.network.disconnect()
            QMessageBox.information(self, "Maintenance Mode", "Computer is entering maintenance mode")
            logger.info("Entering maintenance mode")
            
        except Exception as e:
            logger.error(f"Error entering maintenance mode: {e}")
            QMessageBox.critical(self, "Error", "Failed to enter maintenance mode")

    def handle_computer_removed(self, message: Dict[str, Any]):
        """Handle computer removal event."""
        try:
            self.handle_end_session(message)
            self.network.disconnect()
            QMessageBox.information(self, "Computer Removed", "This computer has been removed from the network")
            logger.info("Computer removed from network")
            
        except Exception as e:
            logger.error(f"Error handling computer removal: {e}")
            QMessageBox.critical(self, "Error", "Failed to handle computer removal")

    def handle_connection_lost(self, message: Dict[str, Any]):
        """Handle connection lost event."""
        try:
            self.status_label.setText("Connection lost")
            self.start_reconnect_countdown(30)  # 30 seconds countdown
            logger.info("Connection lost, starting reconnect countdown")
            
        except Exception as e:
            logger.error(f"Error handling connection lost: {e}")
            QMessageBox.critical(self, "Error", "Failed to handle connection loss")

    def handle_allowed_apps_update(self, message: Dict[str, Any]):
        """Handle allowed apps update event."""
        try:
            allowed_apps = message.get('allowed_apps', [])
            if not allowed_apps:
                return
                
            config_path = Path(__file__).parent.parent / 'data' / 'allowed_apps.json'
            with open(config_path, 'w') as f:
                json.dump(allowed_apps, f, indent=4)
                
            logger.info("Allowed apps updated")
            
        except Exception as e:
            logger.error(f"Error handling allowed apps update: {e}")
            QMessageBox.critical(self, "Error", "Failed to update allowed apps")

    def launch_timer_ui(self, end_time: datetime):
        """Launch the timer UI process."""
        try:
            if self.state.timer_process:
                self.close_timer_ui()
                
            timer_script = Path(__file__).parent / 'timer_ui.py'
            if not timer_script.exists():
                logger.error("Timer UI script not found")
                return
                
            self.state.timer_process = subprocess.Popen(
                [sys.executable, str(timer_script), end_time.isoformat()],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            logger.info("Timer UI launched")
            
        except Exception as e:
            logger.error(f"Error launching timer UI: {e}")
            QMessageBox.critical(self, "Error", "Failed to launch timer UI")

    def close_timer_ui(self):
        """Close the timer UI process."""
        try:
            if self.state.timer_process:
                self.state.timer_process.terminate()
                self.state.timer_process = None
                logger.info("Timer UI closed")
                
        except Exception as e:
            logger.error(f"Error closing timer UI: {e}")
            QMessageBox.critical(self, "Error", "Failed to close timer UI")

    def update_timer_ui(self):
        """Update the timer UI display."""
        try:
            if not self.state.active or not self.state.end_time:
                return
                
            remaining = self.state.end_time - datetime.now()
            if remaining.total_seconds() <= 0:
                self.handle_end_session({})
                return
                
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            seconds = int(remaining.total_seconds() % 60)
            
            self.status_label.setText(f"Time remaining: {hours:02d}:{minutes:02d}:{seconds:02d}")
            
        except Exception as e:
            logger.error(f"Error updating timer UI: {e}")

    def set_connection_ui_visible(self, visible: bool):
        """Set the visibility of connection UI elements."""
        try:
            self.ip_label.setVisible(visible)
            self.ip_input.setVisible(visible)
            self.port_label.setVisible(visible)
            self.port_input.setVisible(visible)
            self.connect_btn.setVisible(visible)
            
        except Exception as e:
            logger.error(f"Error setting connection UI visibility: {e}")

    def load_config(self):
        """Load configuration from file."""
        try:
            config_path = Path(__file__).parent.parent / 'data' / 'client_config.json'
            if not config_path.exists():
                self.server_ip = None
                self.server_port = None
                return
                
            with open(config_path) as f:
                config = json.load(f)
                
            self.server_ip = config.get('server_ip')
            self.server_port = config.get('server_port', 5000)
            
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.server_ip = None
            self.server_port = None

    def try_connect_and_start_timer(self):
        """Attempt to connect to server and start timer."""
        try:
            if not self.server_ip or not self.server_port:
                return
                
            self.connection_progress.setVisible(True)
            self.status_label.setText("Connecting to server...")
            
            if not self.network.connect(self.server_ip, self.server_port):
                self.connection_progress.setVisible(False)
                self.status_label.setText("Connection failed")
                self.start_reconnect_countdown(30)
                
        except Exception as e:
            logger.error(f"Error connecting to server: {e}")
            self.connection_progress.setVisible(False)
            self.status_label.setText("Connection error")
            self.start_reconnect_countdown(30)

    def handle_connect(self):
        """Handle connect button click."""
        try:
            server_ip = self.ip_input.text().strip()
            server_port = int(self.port_input.text().strip())
            
            if not server_ip:
                QMessageBox.warning(self, "Error", "Please enter server IP")
                return
                
            self.connection_progress.setVisible(True)
            self.status_label.setText("Connecting to server...")
            
            if not self.network.connect(server_ip, server_port):
                self.connection_progress.setVisible(False)
                self.status_label.setText("Connection failed")
                QMessageBox.critical(self, "Error", "Failed to connect to server")
                return
                
            # Save config
            config_path = Path(__file__).parent.parent / 'data' / 'client_config.json'
            config = {
                'server_ip': server_ip,
                'server_port': server_port
            }
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
                
            self.server_ip = server_ip
            self.server_port = server_port
            
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid port number")
            self.connection_progress.setVisible(False)
            self.status_label.setText("Invalid port")
        except Exception as e:
            logger.error(f"Error handling connect: {e}")
            self.connection_progress.setVisible(False)
            self.status_label.setText("Connection error")
            QMessageBox.critical(self, "Error", str(e))

    def start_reconnect_countdown(self, seconds: int):
        """Start the reconnection countdown."""
        try:
            self.countdown_label.setText(f"Reconnecting in {seconds} seconds...")
            self.countdown_label.setVisible(True)
            self.connection_timer.start(seconds * 1000)
            
        except Exception as e:
            logger.error(f"Error starting reconnect countdown: {e}")

    def update_reconnect_countdown(self, seconds: int):
        """Update the reconnection countdown display."""
        try:
            self.countdown_label.setText(f"Reconnecting in {seconds} seconds...")
            
        except Exception as e:
            logger.error(f"Error updating reconnect countdown: {e}")

    def handle_connection_status(self, is_connected: bool):
        """Handle connection status change."""
        try:
            self.connection_progress.setVisible(False)
            self.countdown_label.setVisible(False)
            
            if is_connected:
                self.status_label.setText("Connected")
                self.set_connection_ui_visible(False)
            else:
                self.status_label.setText("Disconnected")
                self.set_connection_ui_visible(True)
                
            self.connection_status_changed.emit(is_connected)
            
        except Exception as e:
            logger.error(f"Error handling connection status: {e}")

    def update_status(self):
        """Update the status display."""
        try:
            if not self.state.active:
                return
                
            if self.state.paused:
                self.status_label.setText("Session paused")
                return
                
            self.update_timer_ui()
            
        except Exception as e:
            logger.error(f"Error updating status: {e}")

    def closeEvent(self, event):
        """Handle window close event."""
        try:
            if self.state.active:
                self.handle_end_session({})
            self.network.disconnect()
            event.accept()
            
        except Exception as e:
            logger.error(f"Error in close event: {e}")
            event.accept()

def main():
    """Main entry point for the application."""
    try:
        app = QApplication(sys.argv)
        lock_screen = LockScreen()
        lock_screen.showFullScreen()
        sys.exit(app.exec())
    except Exception as e:
        logger.error(f"Error in main: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 