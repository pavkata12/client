import socket
import json
import threading
import logging
import time
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)

class NetworkManager:
    def __init__(self):
        self.socket = None
        self.message_handlers = {}
        self.connected = False
        self.receive_thread = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5  # seconds

    def connect(self, host: str, port: int) -> bool:
        """Connect to the server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))
            self.connected = True
            self.reconnect_attempts = 0
            
            # Start receive thread
            self.receive_thread = threading.Thread(target=self._receive_messages, daemon=True)
            self.receive_thread.start()
            
            # Send initial status
            self.send_message({
                'type': 'status_update',
                'status': 'online'
            })
            
            return True
        except Exception as e:
            logger.error(f"Error connecting to server: {e}")
            self.connected = False
            return False

    def disconnect(self):
        """Disconnect from the server."""
        try:
            if self.connected:
                self.send_message({
                    'type': 'status_update',
                    'status': 'offline'
                })
        except:
            pass
        finally:
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None

    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self.connected and self.socket is not None

    def send_message(self, message: dict) -> bool:
        """Send a message to the server."""
        if not self.is_connected():
            logger.error("Not connected to server")
            return False
            
        try:
            data = json.dumps(message).encode('utf-8')
            self.socket.sendall(data)
            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self._handle_disconnect()
            return False

    def _receive_messages(self):
        """Receive messages from the server."""
        buffer = ""
        while self.is_connected():
            try:
                data = self.socket.recv(4096)
                if not data:
                    logger.info("Connection closed by server")
                    self._handle_disconnect()
                    break
                    
                buffer += data.decode('utf-8')
                while '\n' in buffer:
                    message_str, buffer = buffer.split('\n', 1)
                    try:
                        message = json.loads(message_str)
                        self._handle_message(message)
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON message: {message_str}")
            except Exception as e:
                logger.error(f"Error receiving message: {e}")
                self._handle_disconnect()
                break

    def _handle_disconnect(self):
        """Handle disconnection from server."""
        self.connected = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            
        # Notify handlers about disconnection
        self._handle_message({'type': 'connection_lost'})

    def _handle_message(self, message: dict):
        """Handle a received message."""
        message_type = message.get('type')
        if message_type in self.message_handlers:
            try:
                self.message_handlers[message_type](message)
            except Exception as e:
                logger.error(f"Error handling message {message_type}: {e}")

    def register_handler(self, message_type: str, handler):
        """Register a message handler."""
        self.message_handlers[message_type] = handler

    def close(self):
        """Clean up resources."""
        self.disconnect()
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0) 