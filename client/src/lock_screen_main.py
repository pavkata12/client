import sys
import os
import subprocess
from PySide6.QtWidgets import QApplication
from lock_screen import LockScreen
from network_manager import NetworkManager

def main():
    app = QApplication(sys.argv)
    lock_screen = LockScreen()
    lock_screen.showFullScreen()

    def on_connect(ip, port):
        # Pass the connected NetworkManager to the main UI
        main_py = os.path.join(os.path.dirname(__file__), 'main.py')
        python_exe = sys.executable
        # Pass the network manager via a global or singleton (simple approach)
        import builtins
        builtins.shared_network_manager = lock_screen.network
        subprocess.Popen([python_exe, main_py])
        app.quit()

    lock_screen.connect_requested.connect(lambda ip, port: on_connect(ip, port))

    sys.exit(app.exec())

if __name__ == "__main__":
    main() 