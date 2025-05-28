import sys
import os
import json
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QToolBar, QMainWindow,
    QDialog, QFormLayout, QLineEdit, QMessageBox,
    QStyle, QStyleFactory, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QSize, QPoint, QEvent
from PySide6.QtGui import QFont, QIcon, QAction, QColor, QPixmap
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
        self.allowed_apps = self.load_allowed_apps()
        self.allowed_apps_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'allowed_apps.json')
        self.allowed_apps_mtime = os.path.getmtime(self.allowed_apps_path) if os.path.exists(self.allowed_apps_path) else None
        
        # Set window properties first
        self.setWindowTitle("Session Desktop")
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.CustomizeWindowHint |
            Qt.WindowSystemMenuHint
        )
        
        # Initialize kiosk controller
        self.kiosk_controller = KioskController()
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Desktop area (for icons)
        self.desktop_widget = QWidget()
        self.desktop_layout = QGridLayout(self.desktop_widget)
        self.desktop_layout.setContentsMargins(40, 80, 40, 40)
        self.desktop_layout.setSpacing(32)
        
        # Add allowed app icons in a grid
        self.build_desktop_icons()
        
        # Timer widget (top-right corner)
        timer_widget = QWidget()
        timer_layout = QVBoxLayout(timer_widget)
        timer_layout.setContentsMargins(0, 0, 24, 0)
        timer_layout.setAlignment(Qt.AlignTop | Qt.AlignRight)
        self.time_label = QLabel("--:--:--")
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        gothic_font = QFont("Arial Black")
        gothic_font.setPointSize(48)
        gothic_font.setBold(True)
        self.time_label.setFont(gothic_font)
        self.time_label.setStyleSheet("color: #ecf0f1;")
        timer_layout.addWidget(self.time_label)
        self.main_layout.addWidget(timer_widget, alignment=Qt.AlignTop | Qt.AlignRight)
        
        # Set window style (desktop look)
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #2c3e50;
            }
            QLabel {
                color: #ecf0f1;
            }
        """)
        
        # Create toolbar after window is fully initialized
        self.create_toolbar()
        
        # Initialize timers
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.update_check_timer = QTimer(self)
        self.update_check_timer.timeout.connect(self.check_for_update)
        self.timer.start(1000)
        self.update_check_timer.start(2000)
        self.update_timer()
        # Poll for allowed_apps.json changes
        self.apps_poll_timer = QTimer(self)
        self.apps_poll_timer.timeout.connect(self.check_allowed_apps_update)
        self.apps_poll_timer.start(5000)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.build_desktop_icons()

    def load_allowed_apps(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'allowed_apps.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading allowed_apps.json: {e}")
        return []

    def get_app_icon(self, app):
        # Try to use custom icon if provided, else use exe icon, else fallback
        if app.get('icon') and os.path.exists(app['icon']):
            return QIcon(app['icon'])
        exe_path = app.get('path')
        if exe_path and os.path.exists(exe_path):
            try:
                import win32api
                import win32con
                import win32ui
                import win32gui
                large, small = win32gui.ExtractIconEx(exe_path, 0)
                if large:
                    icon = QIcon()
                    icon.addPixmap(QPixmap.fromWinHICON(large[0]))
                    win32gui.DestroyIcon(large[0])
                    return icon
            except Exception:
                pass
        # Fallback icon
        return self.style().standardIcon(QStyle.SP_DesktopIcon)

    def launch_application(self, app):
        try:
            exe_path = app.get('path')
            if exe_path and os.path.exists(exe_path):
                os.startfile(exe_path)
                QMessageBox.information(self, "Application Launched", f"{app['name']} is starting...")
            else:
                QMessageBox.warning(self, "Error", f"App path not found: {exe_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error launching {app['name']}: {str(e)}")

    def create_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        
        # Add toolbar actions with icons
        settings_action = QAction(self.style().standardIcon(QStyle.SP_DialogOpenButton), "Settings", self)
        settings_action.triggered.connect(self.show_settings)
        toolbar.addAction(settings_action)
        
        self.addToolBar(toolbar)

    def show_settings(self):
        try:
            dialog = SettingsDialog(self)
            if dialog.exec() == QDialog.Accepted:
                # Settings were saved, you might want to update the kiosk controller
                QMessageBox.information(self, "Settings", "Settings saved successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error in settings dialog: {str(e)}")

    def update_timer(self):
        try:
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
        except Exception as e:
            print(f"Error updating timer: {str(e)}")

    def check_for_update(self):
        try:
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
                except Exception as e:
                    print(f"Error reading update file: {str(e)}")
        except Exception as e:
            print(f"Error checking for updates: {str(e)}")

    def showEvent(self, event):
        """Handle show event to ensure window is fullscreen and stays on top."""
        super().showEvent(event)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def changeEvent(self, event):
        """Prevent window from being minimized and ensure it stays on top."""
        if event.type() == QEvent.WindowStateChange:
            if self.windowState() & Qt.WindowMinimized:
                self.showFullScreen()
            self.raise_()
            self.activateWindow()
        super().changeEvent(event)

    def build_desktop_icons(self):
        # Remove all widgets from the desktop layout
        while self.desktop_layout.count():
            item = self.desktop_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        # Add allowed app icons in a grid, only if the exe exists
        row, col = 0, 0
        max_cols = 5
        icon_size = 80
        for idx, app in enumerate(self.allowed_apps):
            exe_path = app.get('path')
            if not exe_path or not os.path.exists(exe_path):
                continue  # Skip missing executables
            icon_btn = QPushButton()
            icon_btn.setIcon(self.get_app_icon(app))
            icon_btn.setIconSize(QSize(icon_size, icon_size))
            icon_btn.setFixedSize(icon_size + 16, icon_size + 32)
            icon_btn.setToolTip(app['name'])
            icon_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            icon_btn.setStyleSheet("""
                QPushButton {
                    border: none;
                    background: transparent;
                }
                QPushButton:hover {
                    background: #34495e;
                    border-radius: 10px;
                }
            """)
            icon_btn.clicked.connect(lambda checked, a=app: self.launch_application(a))
            label = QLabel(app['name'])
            label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            label.setStyleSheet("color: #ecf0f1; font-size: 14px;")
            label.setWordWrap(True)
            vbox = QVBoxLayout()
            vbox.addWidget(icon_btn, alignment=Qt.AlignHCenter)
            vbox.addWidget(label, alignment=Qt.AlignHCenter)
            vbox.setSpacing(4)
            vbox.setContentsMargins(0, 0, 0, 0)
            icon_widget = QWidget()
            icon_widget.setLayout(vbox)
            self.desktop_layout.addWidget(icon_widget, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def check_allowed_apps_update(self):
        if not os.path.exists(self.allowed_apps_path):
            return
        mtime = os.path.getmtime(self.allowed_apps_path)
        if self.allowed_apps_mtime is None or mtime > self.allowed_apps_mtime:
            self.allowed_apps_mtime = mtime
            self.allowed_apps = self.load_allowed_apps()
            self.build_desktop_icons()
            QMessageBox.information(self, "App List Updated", "The allowed applications list has been updated.")

def main():
    try:
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
        window.raise_()
        window.activateWindow()
        sys.exit(app.exec())
    except Exception as e:
        print(f"Error in main: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 