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

class KioskManager(QObject):
    process_blocked = Signal(str)  # Signal when a process is blocked
    process_allowed = Signal(str)  # Signal when a process is allowed
    kiosk_status_changed = Signal(bool)  # Signal when kiosk mode status changes

    def __init__(self):
        super().__init__()
        self.is_kiosk_mode = False
        self.is_admin = self._is_admin()
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._monitor_processes)
        
        # Default allowed applications
        self.allowed_apps: Dict[str, Dict] = {
            'chrome.exe': {
                'path': r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                'args': ['--kiosk', '--no-first-run', '--no-default-browser-check'],
                'window_title': 'Chrome'
            },
            'firefox.exe': {
                'path': r'C:\Program Files\Mozilla Firefox\firefox.exe',
                'args': ['-kiosk'],
                'window_title': 'Firefox'
            },
            'steam.exe': {
                'path': r'C:\Program Files (x86)\Steam\steam.exe',
                'args': [],
                'window_title': 'Steam'
            },
            'discord.exe': {
                'path': r'C:\Users\%USERNAME%\AppData\Local\Discord\app-*\Discord.exe',
                'args': [],
                'window_title': 'Discord'
            }
        }
        
        # System processes that should always be allowed
        self.system_processes = {
            'explorer.exe',
            'svchost.exe',
            'csrss.exe',
            'winlogon.exe',
            'services.exe',
            'lsass.exe',
            'spoolsv.exe',
            'python.exe',
            'pythonw.exe',
            'GamingCenterClient.exe'
        }

        # Registry keys to modify for kiosk mode
        self.registry_keys = {
            'taskmgr': {
                'key': r'Software\Microsoft\Windows\CurrentVersion\Policies\System',
                'value': 'DisableTaskMgr',
                'type': winreg.REG_DWORD,
                'data': 1
            },
            'cmd': {
                'key': r'Software\Policies\Microsoft\Windows\System',
                'value': 'DisableCMD',
                'type': winreg.REG_DWORD,
                'data': 1
            },
            'regedit': {
                'key': r'Software\Microsoft\Windows\CurrentVersion\Policies\System',
                'value': 'DisableRegistryTools',
                'type': winreg.REG_DWORD,
                'data': 1
            },
            'alt_tab': {
                'key': r'Software\Microsoft\Windows\CurrentVersion\Policies\System',
                'value': 'NoAltTab',
                'type': winreg.REG_DWORD,
                'data': 1
            },
            'win_key': {
                'key': r'Software\Microsoft\Windows\CurrentVersion\Policies\Explorer',
                'value': 'NoWinKeys',
                'type': winreg.REG_DWORD,
                'data': 1
            }
        }

    def _is_admin(self) -> bool:
        """Check if running with administrator privileges."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            return False

    def load_allowed_apps(self, config_path: str) -> None:
        """Load allowed applications from a JSON configuration file."""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                self.allowed_apps.update(config.get('allowed_apps', {}))
        except Exception as e:
            logger.error(f"Error loading allowed apps configuration: {e}")

    def save_allowed_apps(self, config_path: str) -> None:
        """Save allowed applications to a JSON configuration file."""
        try:
            with open(config_path, 'w') as f:
                json.dump({'allowed_apps': self.allowed_apps}, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving allowed apps configuration: {e}")

    def add_allowed_app(self, name: str, path: str, args: List[str] = None, window_title: str = None) -> None:
        """Add an application to the allowed list."""
        self.allowed_apps[name] = {
            'path': path,
            'args': args or [],
            'window_title': window_title or name
        }

    def remove_allowed_app(self, name: str) -> None:
        """Remove an application from the allowed list."""
        self.allowed_apps.pop(name, None)

    def _monitor_processes(self) -> None:
        """Monitor and manage running processes."""
        if not self.is_kiosk_mode:
            return

        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                process_name = proc.info['name'].lower()
                
                # Allow system processes
                if process_name in self.system_processes:
                    continue

                # Check if process is in allowed apps
                if process_name in self.allowed_apps:
                    # Verify the executable path matches
                    if proc.info['exe'] and os.path.exists(proc.info['exe']):
                        continue
                
                # Kill unauthorized process
                proc.kill()
                self.process_blocked.emit(process_name)
                
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

    def _modify_registry(self, key_info: Dict, enable: bool) -> bool:
        """Modify a registry key for kiosk mode."""
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
        """Block system tools by modifying registry."""
        for tool, key_info in self.registry_keys.items():
            self._modify_registry(key_info, True)

    def _unblock_system_tools(self) -> None:
        """Unblock system tools by modifying registry."""
        for tool, key_info in self.registry_keys.items():
            self._modify_registry(key_info, False)

    def start_kiosk_mode(self) -> None:
        """Enable kiosk mode."""
        if not self.is_admin:
            logger.error("Administrator privileges required for kiosk mode")
            return

        self._block_system_tools()
        self.is_kiosk_mode = True
        self.monitor_timer.start(1000)  # Check every second
        self.kiosk_status_changed.emit(True)
        logger.info("Kiosk mode enabled")

    def stop_kiosk_mode(self) -> None:
        """Disable kiosk mode."""
        if not self.is_admin:
            logger.error("Administrator privileges required to disable kiosk mode")
            return

        self._unblock_system_tools()
        self.is_kiosk_mode = False
        self.monitor_timer.stop()
        self.kiosk_status_changed.emit(False)
        logger.info("Kiosk mode disabled")

    def launch_allowed_app(self, app_name: str) -> bool:
        """Launch an allowed application."""
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
        """Get the list of allowed applications."""
        return self.allowed_apps.copy()

    def is_app_allowed(self, app_name: str) -> bool:
        """Check if an application is allowed."""
        return app_name.lower() in self.allowed_apps 