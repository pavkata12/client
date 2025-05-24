    def _update_system_tools_status(self):
        """Update system tools status display."""
        if not self.system_locker.is_admin:
            self.system_tools_status.setText("⚠️ System tools blocking requires administrator privileges")
            self.system_tools_status.setStyleSheet("color: orange;")
            return

        if not self.system_locker.is_monitoring:
            self.system_tools_status.setText("System tools are not blocked")
            self.system_tools_status.setStyleSheet("color: red;")
            return

        blocked_tools = self.system_locker.get_blocked_tools()
        if blocked_tools:
            status = "Blocked: " + ", ".join(blocked_tools)
            self.system_tools_status.setText(status)
            self.system_tools_status.setStyleSheet("color: green;")
        else:
            self.system_tools_status.setText("System tools blocking failed")
            self.system_tools_status.setStyleSheet("color: red;") 