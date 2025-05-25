import os
import sys
import ctypes
import winreg
import subprocess
import json
import psutil
import logging
import time
from typing import List, Set, Dict, Optional
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), '..', 'data', 'logs', 'kiosk.log')),
        logging.StreamHandler()
    ]
)
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
        self.monitor_timer.setInterval(2000)  # Check every 2 seconds
        self.allowed_apps: Dict[str, Dict] = {}
        self.allowed_processes: Set[str] = set([
            'explorer.exe', 'svchost.exe', 'csrss.exe', 'winlogon.exe',
            'services.exe', 'lsass.exe', 'spoolsv.exe', 'python.exe', 'pythonw.exe',
            'SystemSettings.exe', 'RuntimeBroker.exe', 'dwm.exe', 'fontdrvhost.exe',
            'sihost.exe', 'ctfmon.exe', 'WmiPrvSE.exe', 'conhost.exe'
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
        self.registry_backups = {}

    def _is_admin(self) -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
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
                # Validate paths before adding to allowed processes
                for app_name, app_info in self.allowed_apps.items():
                    path = app_info['path']
                    if '*' in path:  # Handle wildcard paths (like Discord)
                        continue
                    if not os.path.exists(path):
                        logger.warning(f"Application path does not exist: {path}")
                        continue
                    self.allowed_processes.add(app_name)
        except Exception as e:
            logger.error(f"Error loading allowed apps configuration: {e}")

    def _monitor_processes(self) -> None:
        if not self.is_kiosk_mode:
            return
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    process_name = proc.info['name'].lower()
                    if process_name in self.allowed_processes:
                        continue
                    
                    # Check if process is a system process
                    if proc.pid <= 4:  # System processes
                        continue
                        
                    # Check if process is a child of an allowed process
                    parent = proc.parent()
                    if parent and parent.name().lower() in self.allowed_processes:
                        continue
                    
                    # Log before killing
                    logger.info(f"Blocking unauthorized process: {process_name} (PID: {proc.pid})")
                    proc.kill()
                    self.process_blocked.emit(process_name)
                    time.sleep(0.1)  # Small delay to prevent CPU overload
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception as e:
                    logger.error(f"Error monitoring process {process_name}: {e}")
        except Exception as e:
            logger.error(f"Error in process monitor: {e}")

    def _backup_registry(self, key_info: Dict) -> None:
        """Backup registry value before modification."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_info['key'], 0, winreg.KEY_READ)
            try:
                value, _ = winreg.QueryValueEx(key, key_info['value'])
                self.registry_backups[key_info['value']] = value
            except WindowsError:
                self.registry_backups[key_info['value']] = None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.error(f"Error backing up registry: {e}")

    def _modify_registry(self, key_info: Dict, enable: bool) -> bool:
        if not self.is_admin:
            logger.error("Administrator privileges required for registry modification")
            return False
        try:
            # Backup current value
            self._backup_registry(key_info)
            
            # Create or open key
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_info['key'])
            try:
                winreg.SetValueEx(
                    key,
                    key_info['value'],
                    0,
                    key_info['type'],
                    1 if enable else 0
                )
                return True
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.error(f"Error modifying registry: {e}")
            return False

    def _restore_registry(self) -> None:
        """Restore registry values from backup."""
        for value_name, value in self.registry_backups.items():
            try:
                for key_info in self.registry_keys.values():
                    if key_info['value'] == value_name:
                        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_info['key'])
                        try:
                            if value is not None:
                                winreg.SetValueEx(
                                    key,
                                    value_name,
                                    0,
                                    key_info['type'],
                                    value
                                )
                            else:
                                winreg.DeleteValue(key, value_name)
                        finally:
                            winreg.CloseKey(key)
                        break
            except Exception as e:
                logger.error(f"Error restoring registry value {value_name}: {e}")

    def _block_system_tools(self) -> None:
        for tool, key_info in self.registry_keys.items():
            if not self._modify_registry(key_info, True):
                logger.error(f"Failed to block {tool}")

    def _unblock_system_tools(self) -> None:
        self._restore_registry()

    def start_kiosk_mode(self) -> None:
        if not self.check_admin():
            return
        try:
            self._block_system_tools()
            self.is_kiosk_mode = True
            self.monitor_timer.start()  # Start the process monitor
            self.kiosk_status_changed.emit(True)
            self.show_message.emit("Kiosk Enabled", "Kiosk mode has been enabled by the administrator.")
            logger.info("Kiosk mode enabled")
        except Exception as e:
            logger.error(f"Error starting kiosk mode: {e}")
            self.stop_kiosk_mode()  # Cleanup on error

    def stop_kiosk_mode(self) -> None:
        if not self.check_admin():
            return
        try:
            self.monitor_timer.stop()  # Stop the process monitor
            self._unblock_system_tools()
            self.is_kiosk_mode = False
            self.kiosk_status_changed.emit(False)
            self.show_message.emit("Kiosk Disabled", "Kiosk mode has been disabled by the administrator.")
            logger.info("Kiosk mode disabled")
        except Exception as e:
            logger.error(f"Error stopping kiosk mode: {e}")

    def launch_allowed_app(self, app_name: str) -> bool:
        if app_name not in self.allowed_apps:
            logger.error(f"Application {app_name} not in allowed list")
            return False
        app_info = self.allowed_apps[app_name]
        try:
            path = app_info['path']
            if '*' in path:  # Handle wildcard paths (like Discord)
                import glob
                matches = glob.glob(path)
                if not matches:
                    logger.error(f"No matching path found for {app_name}")
                    return False
                path = matches[0]
            
            if not os.path.exists(path):
                logger.error(f"Application path does not exist: {path}")
                return False
                
            subprocess.Popen([path] + app_info['args'])
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