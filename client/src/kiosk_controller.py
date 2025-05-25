import os
import sys
import ctypes
import winreg
import subprocess
import json
import psutil
import logging
from typing import List, Set, Dict, Optional
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KioskController(QObject):
    process_blocked = Signal(str)
    kiosk_status_changed = Signal(bool)
    admin_required = Signal()
    show_message = Signal(str, str)  # title, message

    def __init__(self):
        super().__init__()
        self.is_kiosk_mode = False
        self.is_admin = self._is_admin()
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._monitor_processes)
        self.allowed_apps: Dict[str, Dict] = {}
        self.allowed_processes: Set[str] = set([
            'explorer.exe', 'svchost.exe', 'csrss.exe', 'winlogon.exe',
            'services.exe', 'lsass.exe', 'spoolsv.exe', 'python.exe', 'pythonw.exe',
        ])
        self.allowed_windows: Set[str] = set(['Gaming Center Client'])
        self.registry_keys = {
            'taskmgr': {
                'key': r'Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System',
                'value': 'DisableTaskMgr',
                'type': winreg.REG_DWORD,
                'data': 1
            },
            'cmd': {
                'key': r'Software\\Policies\\Microsoft\\Windows\\System',
                'value': 'DisableCMD',
                'type': winreg.REG_DWORD,
                'data': 1
            },
            'regedit': {
                'key': r'Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System',
                'value': 'DisableRegistryTools',
                'type': winreg.REG_DWORD,
                'data': 1
            },
            'alt_tab': {
                'key': r'Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System',
                'value': 'NoAltTab',
                'type': winreg.REG_DWORD,
                'data': 1
            },
            'win_key': {
                'key': r'Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer',
                'value': 'NoWinKeys',
                'type': winreg.REG_DWORD,
                'data': 1
            }
        }

    def _is_admin(self) -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            return False

    def check_admin(self):
        if not self.is_admin:
            logger.error("Administrator privileges required for kiosk mode features.")
            self.admin_required.emit()
            return False
        return True

    def load_allowed_apps(self, config_path: str) -> None:
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                self.allowed_apps = config.get('allowed_apps', {})
                self.allowed_processes.update(self.allowed_apps.keys())
        except Exception as e:
            logger.error(f"Error loading allowed apps configuration: {e}")

    def _monitor_processes(self) -> None:
        if not self.is_kiosk_mode:
            return
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                process_name = proc.info['name'].lower()
                if process_name in self.allowed_processes:
                    continue
                proc.kill()
                self.process_blocked.emit(process_name)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

    def _modify_registry(self, key_info: Dict, enable: bool) -> bool:
        if not self.is_admin:
            logger.error("Administrator privileges required for registry modification")
            return False
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_info['key'])
            winreg.SetValueEx(
                key,
                key_info['value'],
                0,
                key_info['type'],
                1 if enable else 0
            )
            winreg.CloseKey(key)
            return True
        except Exception as e:
            logger.error(f"Error modifying registry: {e}")
            return False

    def _block_system_tools(self) -> None:
        for tool, key_info in self.registry_keys.items():
            self._modify_registry(key_info, True)

    def _unblock_system_tools(self) -> None:
        for tool, key_info in self.registry_keys.items():
            self._modify_registry(key_info, False)

    def start_kiosk_mode(self) -> None:
        if not self.check_admin():
            return
        self._block_system_tools()
        self.is_kiosk_mode = True
        self.kiosk_status_changed.emit(True)
        self.show_message.emit("Kiosk Enabled", "Kiosk mode has been enabled by the administrator.")
        logger.info("Kiosk mode enabled")

    def stop_kiosk_mode(self) -> None:
        if not self.check_admin():
            return
        self._unblock_system_tools()
        self.is_kiosk_mode = False
        self.kiosk_status_changed.emit(False)
        self.show_message.emit("Kiosk Disabled", "Kiosk mode has been disabled by the administrator.")
        logger.info("Kiosk mode disabled")

    def launch_allowed_app(self, app_name: str) -> bool:
        if app_name not in self.allowed_apps:
            logger.error(f"Application {app_name} not in allowed list")
            return False
        app_info = self.allowed_apps[app_name]
        try:
            subprocess.Popen([app_info['path']] + app_info['args'])
            return True
        except Exception as e:
            logger.error(f"Error launching {app_name}: {e}")
            return False

    def get_allowed_apps(self) -> Dict[str, Dict]:
        return self.allowed_apps.copy()

    # --- Advanced blocking stubs ---
    def block_alt_tab(self):
        # Stub: Would require a Windows hook or C extension
        logger.warning("Alt+Tab blocking is not implemented in pure Python.")

    def block_win_key(self):
        # Stub: Would require a Windows hook or C extension
        logger.warning("Windows key blocking is not implemented in pure Python.")

    def enforce_window_focus(self):
        # Stub: Would require pywin32 or similar to enforce allowed window focus
        logger.warning("Window focus enforcement is not implemented.") 