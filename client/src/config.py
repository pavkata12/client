"""
Client configuration settings
"""
import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)

# Network settings
DEFAULT_SERVER_IP = "127.0.0.1"  # localhost
DEFAULT_SERVER_PORT = 5000
SERVICE_NAME = "_gamingcenter._tcp.local."
SERVER_DISCOVERY_TIMEOUT = 5  # seconds

# UI settings
WINDOW_TITLE = "Gaming Center Client"
WINDOW_MIN_WIDTH = 400
WINDOW_MIN_HEIGHT = 300

# System settings
ALLOWED_PROCESSES = {
    'explorer.exe',
    'svchost.exe',
    'csrss.exe',
    'winlogon.exe',
    'services.exe',
    'lsass.exe',
    'spoolsv.exe',
    'python.exe',
    'pythonw.exe'
}

ALLOWED_WINDOWS = {
    'Gaming Center Client',
    'Task Manager',
    'Windows Security'
}

BLOCKED_PROCESSES = [
    "taskmgr.exe",
    "regedit.exe",
    "cmd.exe",
    "powershell.exe",
    "explorer.exe"
]

# Logging settings
LOG_DIR = DATA_DIR / "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = LOG_DIR / "client.log"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_LEVEL = "INFO"

# Date/time format
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# Registry paths
REGISTRY_PATHS = {
    "taskmgr": r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
    "regedit": r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
}

# Registry values
REGISTRY_VALUES = {
    "taskmgr": {
        "name": "DisableTaskMgr",
        "type": "REG_DWORD",
        "value": 1
    },
    "regedit": {
        "name": "DisableRegistryTools",
        "type": "REG_DWORD",
        "value": 1
    }
} 