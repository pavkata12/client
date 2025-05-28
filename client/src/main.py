import sys
import os
import json
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QToolBar, QMainWindow,
    QDialog, QFormLayout, QLineEdit, QMessageBox,
    QStyle, QStyleFactory
)
from PySide6.QtCore import Qt, QTimer, QSize, QPoint
from PySide6.QtGui import QFont, QIcon, QAction, QColor
from kiosk_controller import KioskController

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(300)
        
        layout = QFormLayout(self)
        
        # Add settings fields
        self.server_ip = QLineEdit()
        self.server_port = QLineEdit()
        
        layout.addRow("Server IP:", self.server_ip)
        layout.addRow("Server Port:", self.server_port)
        
        # Load current settings
        self.load_settings()
        
        # Add buttons
        buttons_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        
        save_btn.clicked.connect(self.save_settings)
        cancel_btn.clicked.connect(self.reject)
        
        buttons_layout.addWidget(save_btn)
        buttons_layout.addWidget(cancel_btn)
        layout.addRow(buttons_layout)
    
    def load_settings(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'client_config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.server_ip.setText(config.get('server_ip', ''))
                    self.server_port.setText(str(config.get('server_port', '5000')))
            except Exception:
                pass
    
    def save_settings(self):
        try:
            config = {
                'server_ip': self.server_ip.text().strip(),
                'server_port': int(self.server_port.text().strip())
            }
            config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'client_config.json')
            with open(config_path, 'w') as f:
                json.dump(config, f)
            self.accept()
        except ValueError:
            QMessageBox.warning(self, "Error", "Please enter valid settings")

class TimerWindow(QMainWindow):
    def __init__(self, end_time, update_file):
        super().__init__()
        self.end_time = end_time
        self.update_file = update_file
        self.last_update_mtime = None
        
        # Set window properties first
        self.setWindowTitle("Session Timer")
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.CustomizeWindowHint
        )
        
        # Initialize kiosk controller
        self.kiosk_controller = KioskController()
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Timer display
        timer_layout = QVBoxLayout()
        timer_layout.addStretch(1)
        self.time_label = QLabel("--:--:--")
        self.time_label.setAlignment(Qt.AlignCenter)
        gothic_font = QFont("Old English Text MT")
        gothic_font.setPointSize(96)
        gothic_font.setBold(True)
        self.time_label.setFont(gothic_font)
        timer_layout.addWidget(self.time_label)
        timer_layout.addStretch(1)
        main_layout.addLayout(timer_layout)
        
        # Game and browser icons
        icons_layout = QHBoxLayout()
        icons_layout.addStretch(1)
        
        # Add game icons
        game_icons = [
            ("Steam", "steam.png"),
            ("Discord", "discord.png"),
            ("Chrome", "chrome.png"),
            ("Firefox", "firefox.png")
        ]
        
        for name, icon_file in game_icons:
            icon_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'icons', icon_file)
            if os.path.exists(icon_path):
                icon_btn = QPushButton()
                icon_btn.setIcon(QIcon(icon_path))
                icon_btn.setIconSize(QSize(64, 64))
                icon_btn.setFixedSize(80, 80)
                icon_btn.setToolTip(name)
                icon_btn.setStyleSheet("""
                    QPushButton {
                        border: 2px solid #3498db;
                        border-radius: 10px;
                        background-color: #2980b9;
                        padding: 5px;
                    }
                    QPushButton:hover {
                        background-color: #3498db;
                    }
                    QPushButton:pressed {
                        background-color: #2472a4;
                    }
                """)
                icon_btn.clicked.connect(lambda checked, n=name: self.launch_application(n))
                icons_layout.addWidget(icon_btn)
        
        icons_layout.addStretch(1)
        main_layout.addLayout(icons_layout)
        
        # Set window style
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2c3e50;
            }
            QLabel {
                color: #ecf0f1;
            }
            QToolBar {
                background-color: #34495e;
                border: none;
            }
            QToolButton {
                color: #ecf0f1;
                padding: 5px;
                border: none;
            }
            QToolButton:hover {
                background-color: #2c3e50;
            }
        """)
        
        # Create toolbar after window is fully initialized
        self.create_toolbar()
        
        # Initialize timers
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(1000)
        
        self.update_check_timer = QTimer(self)
        self.update_check_timer.timeout.connect(self.check_for_update)
        self.update_check_timer.start(2000)
        
        # Initial timer update
        self.update_timer()

    def create_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        
        # Add toolbar actions with icons
        settings_action = QAction(self.style().standardIcon(QStyle.SP_DialogOpenButton), "Settings", self)
        settings_action.triggered.connect(self.show_settings)
        toolbar.addAction(settings_action)
        
        self.addToolBar(toolbar)

    def launch_application(self, app_name):
        if self.kiosk_controller.launch_allowed_app(app_name):
            # Show a brief notification
            QMessageBox.information(self, "Application Launched", f"{app_name} is starting...")
        else:
            QMessageBox.warning(self, "Error", f"Failed to launch {app_name}")

    def show_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            # Settings were saved, you might want to update the kiosk controller
            QMessageBox.information(self, "Settings", "Settings saved successfully!")

    def update_timer(self):
        remaining = self.end_time - datetime.now()
        if remaining.total_seconds() > 0:
            total_seconds = int(remaining.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            self.time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            
            # Change color based on remaining time
            if total_seconds < 300:  # Less than 5 minutes
                self.time_label.setStyleSheet("color: #e74c3c;")  # Red
            elif total_seconds < 900:  # Less than 15 minutes
                self.time_label.setStyleSheet("color: #f39c12;")  # Orange
            else:
                self.time_label.setStyleSheet("color: #ecf0f1;")  # White
        else:
            self.time_label.setText("00:00:00")
            self.time_label.setStyleSheet("color: #e74c3c;")  # Red
            self.timer.stop()
            self.update_check_timer.stop()
            QTimer.singleShot(2000, self.close)

    def check_for_update(self):
        if not os.path.exists(self.update_file):
            return
        mtime = os.path.getmtime(self.update_file)
        if self.last_update_mtime is None or mtime > self.last_update_mtime:
            self.last_update_mtime = mtime
            try:
                with open(self.update_file, 'r') as f:
                    data = json.load(f)
                new_end_time = datetime.fromisoformat(data['end_time'])
                if new_end_time > self.end_time:
                    self.end_time = new_end_time
                    QMessageBox.information(self, "Session Extended", "Your session has been extended!")
            except Exception:
                pass

    def showEvent(self, event):
        """Handle show event to ensure window is fullscreen."""
        super().showEvent(event)
        self.showFullScreen()

    def changeEvent(self, event):
        """Prevent window from being minimized."""
        if event.type() == event.WindowStateChange:
            if self.windowState() & Qt.WindowMinimized:
                self.showFullScreen()
        super().changeEvent(event)

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <end_time_iso>")
        sys.exit(1)
    end_time_str = sys.argv[1]
    update_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'timer_update.json')
    try:
        end_time = datetime.fromisoformat(end_time_str)
    except Exception:
        print("Invalid end_time format. Use ISO format, e.g. 2024-06-01T15:30:00")
        sys.exit(1)
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create('Fusion'))  # Use Fusion style for better look
    window = TimerWindow(end_time, update_file)
    window.showFullScreen()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 