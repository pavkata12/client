import sys
from datetime import datetime, timedelta
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

class TimerWindow(QWidget):
    def __init__(self, end_time):
        super().__init__()
        self.end_time = end_time
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

    def update_timer(self):
        remaining = self.end_time - datetime.now()
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            seconds = int(remaining.total_seconds() % 60)
            self.time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        else:
            self.time_label.setText("00:00:00")
            self.timer.stop()
            QTimer.singleShot(2000, self.close)

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <end_time_iso>")
        sys.exit(1)
    end_time_str = sys.argv[1]
    try:
        end_time = datetime.fromisoformat(end_time_str)
    except Exception:
        print("Invalid end_time format. Use ISO format, e.g. 2024-06-01T15:30:00")
        sys.exit(1)
    app = QApplication(sys.argv)
    window = TimerWindow(end_time)
    window.showFullScreen()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 