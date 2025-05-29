import sys
import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QSize
from PySide6.QtGui import QFont, QIcon, QPixmap

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent / 'data' / 'logs' / 'timer_ui.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class TimerState:
    """State management for the timer UI."""
    end_time: Optional[datetime] = None
    is_paused: bool = False
    pause_time: Optional[datetime] = None
    remaining_time: Optional[timedelta] = None

class TimerUI(QMainWindow):
    """Enhanced timer UI with improved display and session management."""
    
    # Signals
    session_ended = Signal()
    session_paused = Signal()
    session_resumed = Signal()
    
    def __init__(self, end_time_str: str):
        """Initialize the timer UI."""
        super().__init__()
        self.state = TimerState()
        self.setup_ui()
        self.setup_window_properties()
        self.setup_timers()
        self.load_state(end_time_str)
        
    def setup_ui(self):
        """Set up the user interface."""
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(20)
        layout.setContentsMargins(50, 50, 50, 50)
        
        # Add logo
        logo_label = QLabel()
        logo_path = Path(__file__).parent.parent / 'assets' / 'logo.png'
        if logo_path.exists():
            logo_pixmap = QPixmap(str(logo_path))
            logo_label.setPixmap(logo_pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)
        
        # Add title
        title_label = QLabel("Gaming Center Timer")
        title_label.setFont(QFont("Arial", 24, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Add timer display
        self.timer_label = QLabel("00:00:00")
        self.timer_label.setFont(QFont("Arial", 48, QFont.Bold))
        self.timer_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.timer_label)
        
        # Add progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Add control buttons
        button_frame = QFrame()
        button_frame.setFrameStyle(QFrame.StyledPanel)
        button_layout = QHBoxLayout(button_frame)
        
        self.pause_button = QPushButton("Pause")
        self.pause_button.setFont(QFont("Arial", 12))
        self.pause_button.setMinimumHeight(40)
        self.pause_button.clicked.connect(self.handle_pause)
        button_layout.addWidget(self.pause_button)
        
        self.resume_button = QPushButton("Resume")
        self.resume_button.setFont(QFont("Arial", 12))
        self.resume_button.setMinimumHeight(40)
        self.resume_button.setVisible(False)
        self.resume_button.clicked.connect(self.handle_resume)
        button_layout.addWidget(self.resume_button)
        
        layout.addWidget(button_frame)
        
        # Apply styles
        self.setup_styles()
        
    def setup_styles(self):
        """Set up application-wide styles."""
        self.setStyleSheet("""
            QWidget {
                background-color: #2c3e50;
                color: #ecf0f1;
            }
            QLabel {
                color: #ecf0f1;
                font-size: 14px;
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
        """Configure window properties."""
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
        """Set up timers for updates."""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(1000)  # Update every second
        
    def load_state(self, end_time_str: str):
        """Load timer state from string."""
        try:
            self.state.end_time = datetime.fromisoformat(end_time_str)
            self.update_display()
            logger.info(f"Timer state loaded with end time: {end_time_str}")
            
        except Exception as e:
            logger.error(f"Error loading timer state: {e}")
            QMessageBox.critical(self, "Error", "Failed to load timer state")
            self.close()
            
    def update_display(self):
        """Update the timer display."""
        try:
            if not self.state.end_time:
                return
                
            if self.state.is_paused:
                if not self.state.remaining_time:
                    self.state.remaining_time = self.state.end_time - self.state.pause_time
                remaining = self.state.remaining_time
            else:
                remaining = self.state.end_time - datetime.now()
                
            if remaining.total_seconds() <= 0:
                self.handle_session_end()
                return
                
            # Update timer label
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            seconds = int(remaining.total_seconds() % 60)
            self.timer_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            
            # Update progress bar
            total_seconds = (self.state.end_time - self.state.pause_time).total_seconds()
            elapsed_seconds = total_seconds - remaining.total_seconds()
            progress = int((elapsed_seconds / total_seconds) * 100)
            self.progress_bar.setValue(progress)
            
        except Exception as e:
            logger.error(f"Error updating display: {e}")
            
    def handle_pause(self):
        """Handle pause button click."""
        try:
            if self.state.is_paused:
                return
                
            self.state.is_paused = True
            self.state.pause_time = datetime.now()
            
            self.pause_button.setVisible(False)
            self.resume_button.setVisible(True)
            
            self.session_paused.emit()
            logger.info("Timer paused")
            
        except Exception as e:
            logger.error(f"Error handling pause: {e}")
            QMessageBox.critical(self, "Error", "Failed to pause timer")
            
    def handle_resume(self):
        """Handle resume button click."""
        try:
            if not self.state.is_paused:
                return
                
            self.state.is_paused = False
            self.state.pause_time = None
            
            if self.state.remaining_time:
                self.state.end_time = datetime.now() + self.state.remaining_time
                self.state.remaining_time = None
                
            self.pause_button.setVisible(True)
            self.resume_button.setVisible(False)
            
            self.session_resumed.emit()
            logger.info("Timer resumed")
            
        except Exception as e:
            logger.error(f"Error handling resume: {e}")
            QMessageBox.critical(self, "Error", "Failed to resume timer")
            
    def handle_session_end(self):
        """Handle session end."""
        try:
            self.session_ended.emit()
            logger.info("Session ended")
            self.close()
            
        except Exception as e:
            logger.error(f"Error handling session end: {e}")
            self.close()
            
    def closeEvent(self, event):
        """Handle window close event."""
        try:
            self.update_timer.stop()
            event.accept()
            
        except Exception as e:
            logger.error(f"Error in close event: {e}")
            event.accept()

def main():
    """Main entry point for the application."""
    try:
        if len(sys.argv) != 2:
            logger.error("Invalid arguments")
            sys.exit(1)
            
        app = QApplication(sys.argv)
        timer_ui = TimerUI(sys.argv[1])
        timer_ui.showFullScreen()
        sys.exit(app.exec())
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 