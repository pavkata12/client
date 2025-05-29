import socket
import json
import logging
import threading
import time
from typing import Dict, Any, Optional, Callable
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from PySide6.QtCore import QObject, Signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent / 'data' / 'logs' / 'network.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class ConnectionState:
    """State management for network connection."""
    connected: bool = False
    server_ip: Optional[str] = None
    server_port: Optional[int] = None
    last_heartbeat: float = 0.0
    reconnect_attempts: int = 0
    max_reconnect_attempts: int = 5
    reconnect_delay: float = 5.0

class NetworkManager(QObject):
    """Enhanced network manager with improved error handling and state management."""
    
    # Signals
    connected = Signal()
    disconnected = Signal()
    message_received = Signal(str, dict)  # message_type, data
    error_occurred = Signal(str)  # error_message
    connection_status_changed = Signal(bool)  # connected
    
    def __init__(self):
        """Initialize the network manager."""
        super().__init__()
        self.state = ConnectionState()
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.lock = threading.Lock()
        self.message_handlers: Dict[str, Callable] = {}
        self.receive_thread: Optional[threading.Thread] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        
    def connect_to_server(self, server_ip: str, server_port: int) -> bool:
        """Connect to the server with timeout and error handling."""
        try:
            if self.state.connected:
                logger.warning("Already connected to server")
                return True
                
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)  # 5 second timeout
            
            try:
                self.socket.connect((server_ip, server_port))
            except (socket.timeout, ConnectionRefusedError) as e:
                logger.error(f"Connection failed: {e}")
                self._cleanup_connection()
                return False
                
            self.socket.settimeout(None)  # Remove timeout after connection
            self.socket.setblocking(False)  # Non-blocking mode
            
            self.state.connected = True
            self.state.server_ip = server_ip
            self.state.server_port = server_port
            self.state.last_heartbeat = time.time()
            self.state.reconnect_attempts = 0
            
            self.running = True
            self._start_threads()
            
            self.connected.emit()
            self.connection_status_changed.emit(True)
            logger.info(f"Connected to server {server_ip}:{server_port}")
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to server: {e}")
            self._cleanup_connection()
            return False
            
    def disconnect(self) -> None:
        """Disconnect from the server and cleanup resources."""
        try:
            self.running = False
            
            if self.socket:
                try:
                    self.socket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                self.socket.close()
                
            if self.receive_thread and self.receive_thread.is_alive():
                self.receive_thread.join(timeout=1.0)
                
            if self.heartbeat_thread and self.heartbeat_thread.is_alive():
                self.heartbeat_thread.join(timeout=1.0)
                
            self._cleanup_connection()
            
            self.disconnected.emit()
            self.connection_status_changed.emit(False)
            logger.info("Disconnected from server")
            
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
            
    def send_message(self, message_type: str, data: Dict[str, Any]) -> bool:
        """Send a message to the server with error handling."""
        try:
            if not self.state.connected or not self.socket:
                logger.error("Not connected to server")
                return False
                
            message = {
                'type': message_type,
                'data': data,
                'timestamp': time.time()
            }
            
            with self.lock:
                try:
                    self.socket.sendall((json.dumps(message) + '\n').encode())
                    return True
                except (socket.error, BrokenPipeError) as e:
                    logger.error(f"Error sending message: {e}")
                    self._handle_connection_lost()
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
            
    def _start_threads(self) -> None:
        """Start receive and heartbeat threads."""
        try:
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            
            self.receive_thread.start()
            self.heartbeat_thread.start()
            
        except Exception as e:
            logger.error(f"Error starting threads: {e}")
            self._cleanup_connection()
            
    def _receive_loop(self) -> None:
        """Receive and process messages from the server."""
        buffer = ""
        
        while self.running:
            try:
                if not self.socket:
                    break
                    
                try:
                    data = self.socket.recv(4096).decode()
                    if not data:
                        break
                    buffer += data
                except BlockingIOError:
                    time.sleep(0.1)
                    continue
                except (socket.error, ConnectionResetError) as e:
                    logger.error(f"Socket error in receive loop: {e}")
                    break
                    
                while '\n' in buffer:
                    message_str, buffer = buffer.split('\n', 1)
                    try:
                        message = json.loads(message_str)
                        message_type = message.get('type')
                        data = message.get('data', {})
                        
                        if message_type:
                            self.message_received.emit(message_type, data)
                            handler = self.message_handlers.get(message_type)
                            if handler:
                                handler(data)
                                
                    except json.JSONDecodeError as e:
                        logger.error(f"Error decoding message: {e}")
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        
            except Exception as e:
                logger.error(f"Error in receive loop: {e}")
                break
                
        self._handle_connection_lost()
        
    def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages to keep connection alive."""
        while self.running:
            try:
                if not self.state.connected:
                    break
                    
                current_time = time.time()
                if current_time - self.state.last_heartbeat >= 30.0:  # 30 second interval
                    if not self.send_message('heartbeat', {}):
                        break
                    self.state.last_heartbeat = current_time
                    
                time.sleep(1.0)
                
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                break
                
        self._handle_connection_lost()
        
    def _handle_connection_lost(self) -> None:
        """Handle connection loss with exponential backoff."""
        try:
            if not self.state.connected:
                return
                
            self.state.connected = False
            self.state.reconnect_attempts += 1
            
            if self.state.reconnect_attempts > self.state.max_reconnect_attempts:
                logger.error("Max reconnection attempts reached")
                self._cleanup_connection()
                self.error_occurred.emit("Connection lost and max reconnection attempts reached")
                return
                
            # Calculate delay with exponential backoff
            delay = min(
                self.state.reconnect_delay * (2 ** (self.state.reconnect_attempts - 1)),
                60.0  # Max delay of 60 seconds
            )
            
            logger.info(f"Connection lost. Attempting to reconnect in {delay:.1f} seconds...")
            self.error_occurred.emit(f"Connection lost. Reconnecting in {delay:.1f} seconds...")
            
            # Start reconnection thread
            threading.Thread(
                target=self._reconnect,
                args=(delay,),
                daemon=True
            ).start()
            
        except Exception as e:
            logger.error(f"Error handling connection loss: {e}")
            self._cleanup_connection()
            
    def _reconnect(self, delay: float) -> None:
        """Attempt to reconnect with delay."""
        try:
            time.sleep(delay)
            
            if not self.state.server_ip or not self.state.server_port:
                logger.error("No server information available for reconnection")
                return
                
            logger.info(f"Attempting to reconnect to {self.state.server_ip}:{self.state.server_port}")
            if self.connect_to_server(self.state.server_ip, self.state.server_port):
                logger.info("Reconnection successful")
                self.state.reconnect_attempts = 0
            else:
                logger.error("Reconnection failed")
                
        except Exception as e:
            logger.error(f"Error during reconnection: {e}")
            
    def _cleanup_connection(self) -> None:
        """Clean up connection resources."""
        try:
            self.state.connected = False
            self.state.server_ip = None
            self.state.server_port = None
            self.state.last_heartbeat = 0.0
            
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
                
        except Exception as e:
            logger.error(f"Error cleaning up connection: {e}")
            
    def register_message_handler(self, message_type: str, handler: Callable) -> None:
        """Register a handler for a specific message type."""
        try:
            self.message_handlers[message_type] = handler
            logger.info(f"Registered handler for message type: {message_type}")
            
        except Exception as e:
            logger.error(f"Error registering message handler: {e}")
            
    def unregister_message_handler(self, message_type: str) -> None:
        """Unregister a message handler."""
        self.message_handlers.pop(message_type, None)
        
    def is_connected(self) -> bool:
        """Check if connected to server."""
        with self.lock:
            return self.state.connected 