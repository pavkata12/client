import sys
import os
import subprocess
from PySide6.QtWidgets import QApplication
from lock_screen import LockScreen

def main():
    app = QApplication(sys.argv)
    lock_screen = LockScreen()
    lock_screen.showFullScreen()

    def on_connect(ip, port):
        # Save IP/port to config (handled in lock_screen)
        # Launch main UI and exit lock screen
        main_py = os.path.join(os.path.dirname(__file__), 'main.py')
        python_exe = sys.executable
        subprocess.Popen([python_exe, main_py])
        app.quit()

    lock_screen.connect_requested.connect(lambda ip, port: on_connect(ip, port))

    sys.exit(app.exec())

if __name__ == "__main__":
    main() 