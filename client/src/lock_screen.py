from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QEvent, QTimer
from PySide6.QtGui import QFont
import os
import json
import keyboard

class LockScreen(QWidget):
    """A fullscreen black lock screen with connection UI."""
    
    # Signal emitted when connection is requested
    connect_requested = Signal(str, int)  # ip, port
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.setup_window_properties()
        self.connection_timer = QTimer(self)
        self.connection_timer.timeout.connect(self.try_reconnect)
        self.server_ip = None
        self.server_port = None
        self.connected = False
        self.load_server_config()
        if self.server_ip and self.server_port:
            self.set_connection_ui_visible(False)
            self.status_label.setText("Connecting to server...")
            self.connection_timer.start(3000)
        else:
            self.set_connection_ui_visible(True)
        
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

    def handle_connect(self):
        """Handle connect button click."""
        try:
            ip = self.ip_input.text().strip()
            port = int(self.port_input.text().strip())
            
            if not ip:
                QMessageBox.warning(self, "Error", "Please enter a server IP address")
                return
                
            self.save_server_config(ip, port)
            self.connect_requested.emit(ip, port)
            
        except ValueError:
            QMessageBox.warning(self, "Error", "Please enter a valid port number")
            
    def try_reconnect(self):
        if not self.connected and self.server_ip and self.server_port:
            self.status_label.setText("Connecting to server...")
            self.connect_requested.emit(self.server_ip, self.server_port)

    def update_status(self, status):
        """Update the status label."""
        self.status_label.setText(f"Status: {status}")
        if status == "Connected to server":
            self.connected = True
            self.connection_timer.stop()
        else:
            self.connected = False
            if self.server_ip and self.server_port:
                if not self.connection_timer.isActive():
                    self.connection_timer.start(3000)
        
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