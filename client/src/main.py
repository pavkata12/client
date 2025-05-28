import sys
import os
import json
from datetime import datetime, timedelta
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

class TimerWindow(QWidget):
    def __init__(self, end_time, update_file):
        super().__init__()
        self.end_time = end_time
        self.update_file = update_file
        self.last_update_mtime = None
        self.setWindowTitle("Session Timer")
        self.setMinimumSize(600, 400)
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        self.time_label = QLabel("--:--:--")
        self.time_label.setAlignment(Qt.AlignCenter)
        gothic_font = QFont("Old English Text MT")
        gothic_font.setPointSize(96)
        gothic_font.setBold(True)
        self.time_label.setFont(gothic_font)
        layout.addWidget(self.time_label)
        layout.addStretch(1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(1000)
        self.update_timer()
        # Timer to check for session extension
        self.update_check_timer = QTimer(self)
        self.update_check_timer.timeout.connect(self.check_for_update)
        self.update_check_timer.start(2000)

    def update_timer(self):
        remaining = self.end_time - datetime.now()
        if remaining.total_seconds() > 0:
            total_seconds = int(remaining.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            self.time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        else:
            self.time_label.setText("00:00:00")
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
            except Exception:
                pass

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
    window = TimerWindow(end_time, update_file)
    window.showFullScreen()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 