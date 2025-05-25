import sys
import os
import subprocess
from PySide6.QtWidgets import QApplication
from lock_screen import LockScreen

def launch_main_ui():
    # Launch the main client UI as a new process
    main_py = os.path.join(os.path.dirname(__file__), 'main.py')
    python_exe = sys.executable
    subprocess.Popen([python_exe, main_py])

def main():
    app = QApplication(sys.argv)
    lock_screen = LockScreen()
    lock_screen.showFullScreen()

    def on_connect(ip, port):
        # When a session starts, launch the main UI and exit lock screen
        launch_main_ui()
        app.quit()

    # Connect the signal for session start (simulate with connect_requested for now)
    lock_screen.connect_requested.connect(lambda ip, port: on_connect(ip, port))

    sys.exit(app.exec())

if __name__ == "__main__":
    main() 