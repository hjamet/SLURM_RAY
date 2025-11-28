import paramiko
import socket
import threading
import logging

class SSHTunnel:
    """Context manager for SSH port forwarding using Paramiko"""
    
    def __init__(
        self,
        ssh_host: str,
        ssh_username: str,
        ssh_password: str,
        remote_host: str,
        local_port: int = 8888,
        remote_port: int = 8888,
        logger: logging.Logger = None
    ):
        """Initialize SSH tunnel
        
        Args:
            ssh_host: SSH server hostname
            ssh_username: SSH username
            ssh_password: SSH password
            remote_host: Remote hostname to forward to
            local_port: Local port to bind (default: 8888)
            remote_port: Remote port to forward (default: 8888)
            logger: Optional logger
        """
        self.ssh_host = ssh_host
        self.ssh_username = ssh_username
        self.ssh_password = ssh_password
        self.remote_host = remote_host
        self.local_port = local_port
        self.remote_port = remote_port
        self.ssh_client = None
        self.forward_server = None
        self.logger = logger
    
    def __enter__(self):
        """Create SSH tunnel"""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_client.connect(
                hostname=self.ssh_host,
                username=self.ssh_username,
                password=self.ssh_password,
            )
            
            # Create local port forwarding using socket server
            transport = self.ssh_client.get_transport()
            
            # Create a local socket server
            local_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            local_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            local_socket.bind(("127.0.0.1", self.local_port))
            if self.local_port == 0:
                self.local_port = local_socket.getsockname()[1]
            local_socket.listen(5)
            self.forward_server = local_socket
            
            def forward_handler(client_socket):
                try:
                    # Create SSH channel to remote host
                    channel = transport.open_channel(
                        "direct-tcpip",
                        (self.remote_host, self.remote_port),
                        client_socket.getpeername(),
                    )
                    
                    # Forward data bidirectionally
                    def forward_data(source, dest):
                        try:
                            while True:
                                data = source.recv(1024)
                                if not data:
                                    break
                                dest.send(data)
                        except Exception:
                            pass
                        finally:
                            source.close()
                            dest.close()
                    
                    # Start forwarding in both directions
                    thread1 = threading.Thread(
                        target=forward_data,
                        args=(client_socket, channel),
                        daemon=True,
                    )
                    thread2 = threading.Thread(
                        target=forward_data,
                        args=(channel, client_socket),
                        daemon=True,
                    )
                    thread1.start()
                    thread2.start()
                    thread1.join()
                    thread2.join()
                except Exception:
                    pass
                finally:
                    client_socket.close()
            
            def accept_handler():
                while True:
                    try:
                        client_socket, addr = self.forward_server.accept()
                        thread = threading.Thread(
                            target=forward_handler,
                            args=(client_socket,),
                            daemon=True,
                        )
                        thread.start()
                    except Exception:
                        break
            
            forward_thread = threading.Thread(target=accept_handler, daemon=True)
            forward_thread.start()
            
            msg = f"SSH tunnel established: localhost:{self.local_port} -> {self.remote_host}:{self.remote_port}"
            print(msg)
            if self.logger:
                self.logger.info(msg)
            return self
        except Exception as e:
            msg = f"Warning: Failed to create SSH tunnel: {e}"
            print(msg)
            print("Dashboard will not be accessible via port forwarding")
            if self.logger:
                self.logger.warning(msg)
                self.logger.info("Dashboard will not be accessible via port forwarding")
            if self.ssh_client:
                self.ssh_client.close()
            self.ssh_client = None
            self.forward_server = None
            return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close SSH tunnel"""
        if self.forward_server:
            try:
                self.forward_server.close()
            except Exception:
                pass
        if self.ssh_client:
            self.ssh_client.close()
        return False

