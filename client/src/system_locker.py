import os
import sys
import ctypes
import winreg
import subprocess
from typing import List, Set, Optional
import psutil
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SystemLocker:
    def __init__(self):
        self.allowed_processes: Set[str] = {
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
        
        self.allowed_windows: Set[str] = {
            'Gaming Center Client',
            'Task Manager',
            ' diWindows Security'
        }

        self.is_monitoring = False
        self.blocked_processes = [
            "taskmgr.exe",
            "regedit.exe",
            "cmd.exe",
            "powershell.exe",
            "explorer.exe"
        ]

        self.is_admin = self._is_admin()
        self.blocked_tools = []
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
            }
        }

    def _is_admin(self) -> bool:
        """Check if running with administrator privileges."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            return False

    def _create_registry_key(self, key_path: str) -> bool:
        """Create registry key if it doesn't exist."""
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
            winreg.CloseKey(key)
            return True
        except Exception as e:
            logger.error(f"Error creating registry key {key_path}: {e}")
            return False

    def _set_registry_value(self, key_path: str, value_name: str, value_type: int, value_data: int) -> bool:
        """Set registry value with proper error handling."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
            winreg.SetValueEx(key, value_name, 0, value_type, value_data)
            winreg.CloseKey(key)
            return True
        except Exception as e:
            logger.error(f"Error setting registry value {value_name}: {e}")
            return False

    def block_system_tools(self) -> bool:
        """Block system tools using registry modifications."""
        if not self.is_admin:
            logger.warning("Running without administrator privileges. Some features may not work.")
            return False

        success = True
        for tool, settings in self.registry_keys.items():
            # Create key if it doesn't exist
            if not self._create_registry_key(settings['key']):
                success = False
                continue

            # Set the value
            if not self._set_registry_value(
                settings['key'],
                settings['value'],
                settings['type'],
                settings['data']
            ):
                success = False
                continue

            self.blocked_tools.append(tool)
            logger.info(f"Blocked {tool}")

        return success

    def unblock_system_tools(self) -> bool:
        """Unblock system tools by removing registry modifications."""
        if not self.is_admin:
            logger.warning("Running without administrator privileges. Some features may not work.")
            return False

        success = True
        for tool in self.blocked_tools:
            settings = self.registry_keys.get(tool)
            if not settings:
                continue

            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, settings['key'], 0, winreg.KEY_WRITE)
                winreg.DeleteValue(key, settings['value'])
                winreg.CloseKey(key)
                logger.info(f"Unblocked {tool}")
            except Exception as e:
                logger.error(f"Error unblocking {tool}: {e}")
                success = False

        self.blocked_tools.clear()
        return success

    def is_tool_blocked(self, tool_name: str) -> bool:
        """Check if a specific tool is blocked."""
        return tool_name in self.blocked_tools

    def get_blocked_tools(self) -> List[str]:
        """Get list of currently blocked tools."""
        return self.blocked_tools.copy()

    def block_task_manager(self):
        """Block access to Task Manager."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Error blocking Task Manager: {e}")

    def unblock_task_manager(self):
        """Unblock access to Task Manager."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Error unblocking Task Manager: {e}")

    def block_registry_editor(self):
        """Block access to Registry Editor."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "DisableRegistryTools", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Error blocking Registry Editor: {e}")

    def unblock_registry_editor(self):
        """Unblock access to Registry Editor."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "DisableRegistryTools", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Error unblocking Registry Editor: {e}")

    def block_alt_tab(self):
        """Block Alt+Tab functionality."""
        # This is a more complex task that requires hooking into the Windows message loop
        # For now, we'll just monitor and kill processes that might be used to switch windows
        pass

    def unblock_alt_tab(self):
        """Unblock Alt+Tab functionality."""
        pass

    def kill_unauthorized_processes(self):
        """Kill processes that are not in the allowed list."""
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'].lower() not in self.allowed_processes:
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

    def add_allowed_process(self, process_name: str):
        """Add a process to the allowed list."""
        self.allowed_processes.add(process_name.lower())

    def remove_allowed_process(self, process_name: str):
        """Remove a process from the allowed list."""
        self.allowed_processes.discard(process_name.lower())

    def add_allowed_window(self, window_title: str):
        """Add a window title to the allowed list."""
        self.allowed_windows.add(window_title)

    def remove_allowed_window(self, window_title: str):
        """Remove a window title from the allowed list."""
        self.allowed_windows.discard(window_title)

    def start_monitoring(self):
        """Start monitoring and blocking system processes."""
        self.is_monitoring = True
        self.block_system_tools()

    def stop_monitoring(self):
        """Stop monitoring and unblock system tools."""
        self.is_monitoring = False
        self.unblock_system_tools()

    def _kill_process(self, process_name: str):
        """Kill a process by name."""
        try:
            subprocess.run(["taskkill", "/F", "/IM", process_name], check=False)
        except Exception as e:
            logger.error(f"Error killing process {process_name}: {e}")

    def check_and_block_processes(self):
        """Check for and block unauthorized processes."""
        if not self.is_monitoring:
            return

        for process in self.blocked_processes:
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {process}"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                if process.lower() in result.stdout.lower():
                    self._kill_process(process)
            except Exception as e:
                logger.error(f"Error checking process {process}: {e}")

    def __enter__(self):
        """Context manager entry."""
        self.start_monitoring()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_monitoring() 