import os
import sys
import ctypes
import winreg
import subprocess
import json
import psutil
import logging
import time
from typing import List, Set, Dict, Optional, Any, Tuple
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent / 'data' / 'logs' / 'kiosk.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class KioskMode(Enum):
    """Enum for kiosk mode states."""
    DISABLED = "disabled"
    ENABLED = "enabled"
    TRANSITIONING = "transitioning"

@dataclass
class AppConfig:
    """Configuration for allowed applications."""
    name: str
    path: str
    args: List[str] = None
    window_title: str = None
    icon_path: str = None

class KioskController(QObject):
    """Enhanced controller for managing kiosk mode and system restrictions."""
    
    # Signals
    process_blocked = Signal(str)  # Process name
    process_allowed = Signal(str)  # Process name
    kiosk_mode_changed = Signal(bool)  # Is enabled
    admin_required = Signal()
    show_message = Signal(str, str)  # title, message
    app_launch_failed = Signal(str, str)  # app_name, error_message

    def __init__(self):
        """Initialize the kiosk controller with enhanced functionality."""
        super().__init__()
        self.mode = KioskMode.DISABLED
        self.is_admin = self._is_admin()
        self.setup_timer()
        self.setup_process_lists()
        self.setup_registry_keys()
        self.setup_app_config()
        self.registry_backups = {}
        self.process_cache = {}  # Cache for process information
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5 minutes
        self.allowed_processes: Set[str] = set()
        self.blocked_processes: Set[str] = set()
        self.running_apps: Dict[str, subprocess.Popen] = {}

    def setup_timer(self) -> None:
        """Setup the process monitoring timer with cleanup."""
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._monitor_processes)
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self._cleanup_resources)
        self.cleanup_timer.start(60000)  # Run cleanup every minute

    def setup_process_lists(self) -> None:
        """Initialize system process lists with enhanced categorization."""
        # System processes that should always be allowed
        self.system_processes: Set[str] = {
            'explorer.exe', 'svchost.exe', 'csrss.exe', 'winlogon.exe',
            'services.exe', 'lsass.exe', 'spoolsv.exe', 'python.exe',
            'pythonw.exe', 'System', 'System Idle Process', 'conhost.exe',
            'dwm.exe', 'fontdrvhost.exe', 'sihost.exe', 'taskhostw.exe',
            'RuntimeBroker.exe', 'ctfmon.exe', 'SecurityHealthService.exe'
        }

        # Processes that should be allowed but monitored
        self.monitored_processes: Set[str] = {
            'chrome.exe', 'firefox.exe', 'msedge.exe', 'opera.exe',
            'brave.exe', 'discord.exe', 'steam.exe', 'epicgameslauncher.exe'
        }

    def setup_registry_keys(self) -> None:
        """Initialize registry key configurations with enhanced security."""
        self.registry_keys = {
            'taskmgr': {
                'key': r'Software\Microsoft\Windows\CurrentVersion\Policies\System',
                'value': 'DisableTaskMgr',
                'type': winreg.REG_DWORD,
                'data': 1,
                'backup': True
            },
            'cmd': {
                'key': r'Software\Policies\Microsoft\Windows\System',
                'value': 'DisableCMD',
                'type': winreg.REG_DWORD,
                'data': 1,
                'backup': True
            },
            'regedit': {
                'key': r'Software\Microsoft\Windows\CurrentVersion\Policies\System',
                'value': 'DisableRegistryTools',
                'type': winreg.REG_DWORD,
                'data': 1,
                'backup': True
            },
            'alt_tab': {
                'key': r'Software\Microsoft\Windows\CurrentVersion\Policies\System',
                'value': 'NoAltTab',
                'type': winreg.REG_DWORD,
                'data': 1,
                'backup': True
            },
            'win_key': {
                'key': r'Software\Microsoft\Windows\CurrentVersion\Policies\Explorer',
                'value': 'NoWinKeys',
                'type': winreg.REG_DWORD,
                'data': 1,
                'backup': True
            }
        }

    def setup_app_config(self) -> None:
        """Load and setup application configurations."""
        try:
            config_path = Path(__file__).parent.parent / 'data' / 'allowed_apps.json'
            if config_path.exists():
                with open(config_path, 'r') as f:
                    apps_data = json.load(f)
                    self.allowed_apps = {
                        name: AppConfig(
                            name=name,
                            path=data['path'],
                            args=data.get('args', []),
                            window_title=data.get('window_title'),
                            icon_path=data.get('icon_path')
                        )
                        for name, data in apps_data.items()
                    }
            else:
                self.allowed_apps = {}
                logger.warning("No allowed apps configuration found")
        except Exception as e:
            logger.error(f"Error loading app configuration: {e}")
            self.allowed_apps = {}

    def _is_admin(self) -> bool:
        """Check if running with administrator privileges."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            return False

    def check_admin(self) -> bool:
        """Verify administrator privileges with enhanced error handling."""
        if not self.is_admin:
            logger.error("Administrator privileges required for kiosk mode features")
            self.admin_required.emit()
            return False
        return True

    def _cleanup_resources(self) -> None:
        """Clean up system resources and process cache."""
        try:
            current_time = time.time()
            if current_time - self.last_cleanup >= self.cleanup_interval:
                # Clear process cache
                self.process_cache.clear()
                # Force garbage collection
                import gc
                gc.collect()
                self.last_cleanup = current_time
                logger.debug("Resource cleanup completed")
        except Exception as e:
            logger.error(f"Error during resource cleanup: {e}")

    def _monitor_processes(self) -> None:
        """Enhanced process monitoring with caching and better error handling."""
        if self.mode != KioskMode.ENABLED:
            return

        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'username']):
                try:
                    process_name = proc.info['name'].lower()
                    
                    # Skip if process is in cache and still valid
                    if process_name in self.process_cache:
                        if psutil.pid_exists(self.process_cache[process_name]):
                            continue
                        else:
                            del self.process_cache[process_name]
                    
                    # Skip system processes
                    if process_name in self.system_processes:
                        continue
                    
                    # Skip processes with PID <= 4 (system processes)
                    if proc.pid <= 4:
                        continue
                    
                    # Skip child processes of allowed processes
                    parent = proc.parent()
                    if parent and parent.name().lower() in self.system_processes:
                        continue
                    
                    # Check if process is allowed
                    if process_name in self.monitored_processes:
                        self.process_cache[process_name] = proc.pid
                        continue
                    
                    # Kill unauthorized process
                    logger.info(f"Blocking unauthorized process: {process_name} (PID: {proc.pid})")
                    proc.kill()
                    self.process_blocked.emit(process_name)
                    time.sleep(0.1)  # Prevent CPU overload
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception as e:
                    logger.error(f"Error monitoring process {process_name}: {e}")
        except Exception as e:
            logger.error(f"Error in process monitor: {e}")

    def _modify_registry(self, key_info: Dict[str, Any], enable: bool) -> bool:
        """Modify registry with enhanced error handling and validation."""
        if not self.is_admin:
            logger.error("Administrator privileges required for registry modification")
            return False

        try:
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

    def _backup_registry(self) -> None:
        """Backup registry values with enhanced error handling."""
        for tool, key_info in self.registry_keys.items():
            if not key_info.get('backup', True):
                continue
                
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_info['key'], 0, winreg.KEY_READ)
                try:
                    value, _ = winreg.QueryValueEx(key, key_info['value'])
                    self.registry_backups[key_info['value']] = value
                except FileNotFoundError:
                    self.registry_backups[key_info['value']] = None
                finally:
                    winreg.CloseKey(key)
            except Exception as e:
                logger.error(f"Error backing up registry value {key_info['value']}: {e}")

    def _restore_registry(self) -> None:
        """Restore registry values with enhanced error handling."""
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

    def enable_kiosk_mode(self) -> bool:
        """Enable kiosk mode with enhanced error handling."""
        try:
            if self.mode == KioskMode.ENABLED:
                return True
                
            self.mode = KioskMode.TRANSITIONING
            logger.info("Enabling kiosk mode")
            
            # Backup registry keys
            self._backup_registry_keys()
            
            # Configure registry
            self._configure_registry()
            
            # Kill blocked processes
            self._kill_blocked_processes()
            
            # Start allowed applications
            self._start_allowed_apps()
            
            self.mode = KioskMode.ENABLED
            self.kiosk_mode_changed.emit(True)
            logger.info("Kiosk mode enabled")
            return True
            
        except Exception as e:
            logger.error(f"Error enabling kiosk mode: {e}")
            self._restore_registry_keys()
            self.mode = KioskMode.DISABLED
            return False
            
    def disable_kiosk_mode(self) -> bool:
        """Disable kiosk mode with cleanup."""
        try:
            if self.mode == KioskMode.DISABLED:
                return True
                
            self.mode = KioskMode.TRANSITIONING
            logger.info("Disabling kiosk mode")
            
            # Stop running applications
            self._stop_running_apps()
            
            # Restore registry keys
            self._restore_registry_keys()
            
            # Clear process cache
            self.process_cache.clear()
            
            self.mode = KioskMode.DISABLED
            self.kiosk_mode_changed.emit(False)
            logger.info("Kiosk mode disabled")
            return True
            
        except Exception as e:
            logger.error(f"Error disabling kiosk mode: {e}")
            self.mode = KioskMode.DISABLED
            return False
            
    def _backup_registry_keys(self) -> None:
        """Backup registry keys before modification."""
        try:
            keys_to_backup = [
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Policies\System"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer")
            ]
            
            for hkey, key_path in keys_to_backup:
                try:
                    key = winreg.OpenKey(hkey, key_path, 0, winreg.KEY_READ)
                    values = {}
                    i = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, i)
                            values[name] = value
                            i += 1
                        except WindowsError:
                            break
                    winreg.CloseKey(key)
                    
                    backup_path = Path(__file__).parent.parent / 'data' / 'backup' / f"{key_path.replace('\\', '_')}.json"
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(backup_path, 'w') as f:
                        json.dump(values, f)
                        
                except WindowsError as e:
                    logger.warning(f"Error backing up registry key {key_path}: {e}")
                    
        except Exception as e:
            logger.error(f"Error backing up registry keys: {e}")
            raise
            
    def _restore_registry_keys(self) -> None:
        """Restore registry keys from backup."""
        try:
            keys_to_restore = [
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Policies\System"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer")
            ]
            
            for hkey, key_path in keys_to_restore:
                try:
                    backup_path = Path(__file__).parent.parent / 'data' / 'backup' / f"{key_path.replace('\\', '_')}.json"
                    if not backup_path.exists():
                        continue
                        
                    with open(backup_path) as f:
                        values = json.load(f)
                        
                    key = winreg.OpenKey(hkey, key_path, 0, winreg.KEY_WRITE)
                    for name, value in values.items():
                        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
                    winreg.CloseKey(key)
                    
                except WindowsError as e:
                    logger.warning(f"Error restoring registry key {key_path}: {e}")
                    
        except Exception as e:
            logger.error(f"Error restoring registry keys: {e}")
            raise
            
    def _configure_registry(self) -> None:
        """Configure registry for kiosk mode."""
        try:
            # Disable task manager
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0,
                winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            
            # Disable registry editor
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0,
                winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "DisableRegistryTools", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            
            # Disable run dialog
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer",
                0,
                winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "NoRun", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            
        except Exception as e:
            logger.error(f"Error configuring registry: {e}")
            raise
            
    def _kill_blocked_processes(self) -> None:
        """Kill blocked processes with error handling."""
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'].lower() in self.blocked_processes:
                        proc.kill()
                        logger.info(f"Killed blocked process: {proc.info['name']}")
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                    
        except Exception as e:
            logger.error(f"Error killing blocked processes: {e}")
            raise
            
    def _start_allowed_apps(self) -> None:
        """Start allowed applications with error handling."""
        try:
            config_path = Path(__file__).parent.parent / 'data' / 'allowed_apps.json'
            if not config_path.exists():
                logger.warning("No allowed apps configuration found")
                return
                
            with open(config_path) as f:
                apps = json.load(f)
                
            for app in apps:
                try:
                    config = AppConfig(**app)
                    self._launch_app(config)
                except Exception as e:
                    logger.error(f"Error starting app {app.get('name', 'unknown')}: {e}")
                    self.app_launch_failed.emit(app.get('name', 'unknown'), str(e))
                    
        except Exception as e:
            logger.error(f"Error starting allowed apps: {e}")
            raise
            
    def _launch_app(self, config: AppConfig) -> None:
        """Launch an application with error handling."""
        try:
            if config.name in self.running_apps:
                logger.warning(f"App {config.name} is already running")
                return
                
            # Handle wildcard paths
            if '*' in config.path:
                import glob
                paths = glob.glob(config.path)
                if not paths:
                    raise FileNotFoundError(f"No files found matching pattern: {config.path}")
                config.path = paths[0]
                
            if not os.path.exists(config.path):
                raise FileNotFoundError(f"Application not found: {config.path}")
                
            process = subprocess.Popen(
                [config.path] + config.args,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            self.running_apps[config.name] = process
            logger.info(f"Started application: {config.name}")
            
        except Exception as e:
            logger.error(f"Error launching app {config.name}: {e}")
            raise
            
    def _stop_running_apps(self) -> None:
        """Stop running applications with cleanup."""
        try:
            for name, process in list(self.running_apps.items()):
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                except Exception as e:
                    logger.error(f"Error stopping app {name}: {e}")
                    
            self.running_apps.clear()
            
        except Exception as e:
            logger.error(f"Error stopping running apps: {e}")
            raise

    def update_process_lists(self, allowed: Set[str], blocked: Set[str]) -> None:
        """Update process lists with validation."""
        try:
            self.allowed_processes = {p.lower() for p in allowed}
            self.blocked_processes = {p.lower() for p in blocked}
            
            if self.mode == KioskMode.ENABLED:
                self._kill_blocked_processes()
                
        except Exception as e:
            logger.error(f"Error updating process lists: {e}")
            raise
            
    def check_process(self, process_name: str) -> bool:
        """Check if a process is allowed with caching."""
        try:
            current_time = time.time()
            if current_time - self.last_cleanup > self.cleanup_interval:
                self._cleanup_process_cache()
                
            process_name = process_name.lower()
            if process_name in self.allowed_processes:
                self.process_allowed.emit(process_name)
                return True
                
            if process_name in self.blocked_processes:
                self.process_blocked.emit(process_name)
                return False
                
            # Check process cache
            if process_name in self.process_cache:
                processes = self.process_cache[process_name]
                if any(p.is_running() for p in processes):
                    self.process_allowed.emit(process_name)
                    return True
                    
            # Update process cache
            self.process_cache[process_name] = [
                p for p in psutil.process_iter(['pid', 'name'])
                if p.info['name'].lower() == process_name
            ]
            
            if self.process_cache[process_name]:
                self.process_allowed.emit(process_name)
                return True
                
            self.process_blocked.emit(process_name)
            return False
            
        except Exception as e:
            logger.error(f"Error checking process {process_name}: {e}")
            return False
            
    def _cleanup_process_cache(self) -> None:
        """Clean up process cache."""
        try:
            current_time = time.time()
            self.last_cleanup = current_time
            
            for name, processes in list(self.process_cache.items()):
                self.process_cache[name] = [
                    p for p in processes
                    if p.is_running()
                ]
                if not self.process_cache[name]:
                    del self.process_cache[name]
                    
        except Exception as e:
            logger.error(f"Error cleaning up process cache: {e}")
            
    def is_kiosk_mode_enabled(self) -> bool:
        """Check if kiosk mode is enabled."""
        return self.mode == KioskMode.ENABLED

    def launch_allowed_app(self, app_name: str) -> bool:
        """Launch an allowed application with enhanced error handling."""
        try:
            if app_name not in self.allowed_apps:
                logger.error(f"Application {app_name} not in allowed list")
                return False

            app_config = self.allowed_apps[app_name]
            path = app_config.path
            
            if '*' in path:  # Handle wildcard paths
                import glob
                matches = glob.glob(path)
                if not matches:
                    logger.error(f"No matching path found for {app_name}")
                    return False
                path = matches[0]
            
            if not os.path.exists(path):
                error_msg = f"Application path does not exist: {path}"
                logger.error(error_msg)
                self.app_launch_failed.emit(app_name, error_msg)
                return False
                
            subprocess.Popen([path] + (app_config.args or []))
            return True
        except Exception as e:
            error_msg = f"Error launching {app_name}: {e}"
            logger.error(error_msg)
            self.app_launch_failed.emit(app_name, error_msg)
            return False

    def get_allowed_apps(self) -> Dict[str, AppConfig]:
        """Get the list of allowed applications."""
        return self.allowed_apps.copy()

    def get_kiosk_status(self) -> Tuple[bool, str]:
        """Get detailed kiosk mode status."""
        status_map = {
            KioskMode.DISABLED: "Disabled",
            KioskMode.ENABLED: "Enabled",
            KioskMode.TRANSITIONING: "Transitioning"
        }
        return self.is_kiosk_mode_enabled(), status_map[self.mode]

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