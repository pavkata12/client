import sys
import os
import json
import logging
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QToolBar, QMainWindow,
    QDialog, QFormLayout, QLineEdit, QMessageBox,
    QStyle, QStyleFactory, QSizePolicy, QSystemTrayIcon, QMenu,
    QProgressBar
)
from PySide6.QtCore import Qt, QTimer, QSize, QPoint, QEvent, QFileSystemWatcher, Signal, Slot
from PySide6.QtGui import QFont, QIcon, QAction, QColor, QPixmap, QPalette
from kiosk_controller import KioskController, AppConfig
import subprocess
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent / 'data' / 'logs' / 'main.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class TimerState:
    """State management for the timer window."""
    end_time: datetime
    is_paused: bool = False
    pause_time: Optional[datetime] = None
    remaining_time: Optional[timedelta] = None

class SettingsDialog(QDialog):
    """Dialog for configuring client settings."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(300)
        self.setup_ui()
        self.load_settings()
    
    def setup_ui(self):
        """Initialize the UI components."""
        layout = QFormLayout(self)
        
        # Server settings
        self.server_ip = QLineEdit()
        self.server_port = QLineEdit()
        layout.addRow("Server IP:", self.server_ip)
        layout.addRow("Server Port:", self.server_port)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        
        save_btn.clicked.connect(self.save_settings)
        cancel_btn.clicked.connect(self.reject)
        
        buttons_layout.addWidget(save_btn)
        buttons_layout.addWidget(cancel_btn)
        layout.addRow("", buttons_layout)
    
    def load_settings(self):
        """Load settings from config file."""
        try:
            config_path = Path(__file__).parent.parent / 'data' / 'client_config.json'
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.server_ip.setText(config.get('server_ip', ''))
                    self.server_port.setText(str(config.get('server_port', '5000')))
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
    
    def save_settings(self):
        """Save settings to config file."""
        try:
            config = {
                'server_ip': self.server_ip.text().strip(),
                'server_port': int(self.server_port.text().strip())
            }
            config_path = Path(__file__).parent.parent / 'data' / 'client_config.json'
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            self.accept()
        except ValueError:
            QMessageBox.warning(self, "Error", "Please enter valid settings")
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")

class TimerWindow(QMainWindow):
    """Enhanced timer window with desktop icons and countdown display."""
    
    # Signals
    session_ended = Signal()
    session_paused = Signal()
    session_resumed = Signal()
    app_launch_requested = Signal(str)  # app_name
    
    def __init__(self, end_time: datetime, update_file: Path):
        super().__init__()
        self.state = TimerState(end_time=end_time)
        self.update_file = update_file
        self.kiosk_controller = KioskController()
        self.setup_ui()
        self.setup_timer()
        self.setup_file_watcher()
        self.setup_connections()
        self.load_allowed_apps()
        self.showFullScreen()

    def setup_ui(self):
        """Initialize the UI components with enhanced styling."""
        self.setWindowTitle("Gaming Center Timer")
        self.setup_styles()

        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # Timer display
        timer_container = QWidget()
        timer_layout = QVBoxLayout(timer_container)
        
        self.timer_label = QLabel()
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet("""
            QLabel {
                font-size: 48px;
                font-weight: bold;
                color: #ecf0f1;
                background-color: #2c3e50;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        timer_layout.addWidget(self.timer_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
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
        self.progress_bar.setRange(0, 100)
        timer_layout.addWidget(self.progress_bar)
        
        layout.addWidget(timer_container)

        # Desktop icons layout
        self.desktop_layout = QGridLayout()
        self.desktop_layout.setSpacing(20)
        self.build_desktop_icons()
        layout.addLayout(self.desktop_layout)

    def setup_styles(self):
        """Setup application-wide styles."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2c3e50;
            }
            QWidget {
                color: #ecf0f1;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #2472a4;
            }
            QLabel {
                color: #ecf0f1;
            }
        """)

    def setup_connections(self):
        """Setup signal connections."""
        self.kiosk_controller.process_blocked.connect(self.handle_process_blocked)
        self.kiosk_controller.app_launch_failed.connect(self.handle_app_launch_failed)
        self.app_launch_requested.connect(self.kiosk_controller.launch_allowed_app)

    def handle_process_blocked(self, process_name: str):
        """Handle blocked process notification."""
        logger.info(f"Process blocked: {process_name}")

    def handle_app_launch_failed(self, app_name: str, error: str):
        """Handle application launch failure."""
        QMessageBox.warning(self, "Launch Failed", f"Failed to launch {app_name}: {error}")

    def build_desktop_icons(self):
        """Build the desktop icons with enhanced layout."""
        # Clear existing icons
        while self.desktop_layout.count():
            item = self.desktop_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add allowed app icons in a grid
        row, col = 0, 0
        max_cols = 5
        icon_size = 80

        for app_name, app_config in self.kiosk_controller.get_allowed_apps().items():
            icon_btn = self.create_app_icon(app_config, icon_size)
            self.desktop_layout.addWidget(icon_btn, row, col)
            
            label = QLabel(app_config.name)
            label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            label.setStyleSheet("""
                QLabel {
                    color: #ecf0f1;
                    font-size: 12px;
                    margin-top: 5px;
                }
            """)
            self.desktop_layout.addWidget(label, row + 1, col)

            col += 1
            if col >= max_cols:
                col = 0
                row += 2

    def create_app_icon(self, app_config: AppConfig, icon_size: int) -> QPushButton:
        """Create an application icon button with enhanced styling."""
        icon_btn = QPushButton()
        icon_btn.setIcon(self.get_app_icon(app_config))
        icon_btn.setIconSize(QSize(icon_size, icon_size))
        icon_btn.setFixedSize(icon_size + 16, icon_size + 32)
        icon_btn.setToolTip(f"{app_config.name}\nPath: {app_config.path}")
        icon_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        icon_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                padding: 5px;
            }
            QPushButton:hover {
                background: #34495e;
                border-radius: 10px;
            }
            QPushButton:pressed {
                background: #2c3e50;
            }
        """)
        icon_btn.clicked.connect(lambda: self.app_launch_requested.emit(app_config.name))
        return icon_btn

    def get_app_icon(self, app_config: AppConfig) -> QIcon:
        """Get the application icon with enhanced error handling."""
        try:
            if app_config.icon_path and os.path.exists(app_config.icon_path):
                return QIcon(app_config.icon_path)
            
            path = app_config.path
            if not path or not os.path.exists(path):
                return QIcon.fromTheme("application-x-executable")
                
            return QIcon(path)
        except Exception as e:
            logger.error(f"Error getting icon for {app_config.name}: {e}")
            return QIcon.fromTheme("application-x-executable")

    def load_allowed_apps(self):
        """Load allowed applications with enhanced error handling."""
        try:
            self.build_desktop_icons()
        except Exception as e:
            logger.error(f"Error loading allowed apps: {e}")

    def setup_timer(self):
        """Setup the countdown timer with enhanced functionality."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(1000)

    def setup_file_watcher(self):
        """Setup file watcher for allowed apps updates."""
        self.file_watcher = QFileSystemWatcher([str(self.update_file)], self)
        self.file_watcher.fileChanged.connect(self.handle_file_update)

    def handle_file_update(self):
        """Handle updates to the allowed apps file."""
        try:
            if self.update_file.exists():
                with open(self.update_file, 'r') as f:
                    data = json.load(f)
                    if 'end_time' in data:
                        self.state.end_time = datetime.fromisoformat(data['end_time'])
                    if 'is_paused' in data:
                        self.state.is_paused = data['is_paused']
                        if self.state.is_paused:
                            self.session_paused.emit()
                        else:
                            self.session_resumed.emit()
        except Exception as e:
            logger.error(f"Error handling file update: {e}")

    def update_timer(self):
        """Update the timer display with enhanced functionality."""
        try:
            if self.state.is_paused:
                if self.state.remaining_time:
                    remaining = self.state.remaining_time
                else:
                    remaining = timedelta(0)
            else:
                remaining = self.state.end_time - datetime.now()
                if remaining.total_seconds() <= 0:
                    self.session_ended.emit()
                    self.close()
                    return

            # Update timer label
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.timer_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

            # Update progress bar
            total_seconds = (self.state.end_time - datetime.now()).total_seconds()
            if total_seconds > 0:
                progress = int((total_seconds / (self.state.end_time - datetime.now()).total_seconds()) * 100)
                self.progress_bar.setValue(progress)

        except Exception as e:
            logger.error(f"Error updating timer: {e}")

    def closeEvent(self, event):
        """Handle window close event."""
        try:
            self.timer.stop()
            self.file_watcher.removePath(str(self.update_file))
            super().closeEvent(event)
        except Exception as e:
            logger.error(f"Error in close event: {e}")
            event.accept()

def main():
    """Main function with enhanced error handling."""
    try:
        app = QApplication(sys.argv)
        
        # Parse command line arguments
        if len(sys.argv) < 2:
            logger.error("End time argument required")
            return 1
            
        try:
            end_time = datetime.fromisoformat(sys.argv[1])
        except ValueError:
            logger.error("Invalid end time format. Use ISO format.")
            return 1
            
        # Setup update file
        update_file = Path(__file__).parent.parent / 'data' / 'timer_update.json'
        update_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Create and show window
        window = TimerWindow(end_time, update_file)
        window.show()
        
        return app.exec()
    except Exception as e:
        logger.error(f"Error in main: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 