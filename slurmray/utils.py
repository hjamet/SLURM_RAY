import paramiko
import socket
import threading
import logging
import os
import re
import hashlib


class DependencyManager:
    """Manage dependencies and cache for remote execution"""

    def __init__(self, project_path, logger=None):
        self.project_path = project_path
        self.logger = logger
        self.cache_dir = os.path.join(project_path, ".slogs")
        self.cache_file = os.path.join(self.cache_dir, "requirements_cache.txt")
        self.venv_hash_file = os.path.join(self.cache_dir, "venv_hash.txt")
        self.env_hash_file = os.path.join(self.cache_dir, "env_hash.txt")

        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def parse_requirements(self, req_lines):
        """Parse requirements into dict {package_lower: {original, version}}"""
        reqs = {}
        for line in req_lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Handle 'package==version', 'package>=version', 'package'
            # We split by logical operators to isolate package name
            # For cache comparison, we primarily care about package name and '==' version

            # Simple split for '=='
            if "==" in line:
                parts = line.split("==")
                name_part = parts[0]
                version = parts[1].split(";")[0].strip()  # Remove env markers
            else:
                # Split by other operators or spaces
                # re.split returns the parts, we take the first one as name
                name_part = re.split(r"[<>=;]", line)[0]
                version = None

            name = name_part.strip().lower()

            # Clean name from extras e.g. ray[default] -> ray
            if "[" in name:
                name = name.split("[")[0]

            reqs[name] = {"original": line, "version": version}
        return reqs

    def load_cache(self):
        """Load cached requirements"""
        if not os.path.exists(self.cache_file):
            return []
        with open(self.cache_file, "r") as f:
            return f.readlines()

    def save_cache(self, remote_reqs_lines):
        """Save remote requirements to cache"""
        with open(self.cache_file, "w") as f:
            f.writelines(remote_reqs_lines)

    def compare(self, local_reqs_lines, remote_reqs_lines):
        """
        Compare local requirements with remote/cache.
        Returns a list of lines (requirements) that need to be installed.
        """
        local_reqs = self.parse_requirements(local_reqs_lines)
        remote_reqs = self.parse_requirements(remote_reqs_lines)

        to_install = []

        for name, info in local_reqs.items():
            local_ver = info["version"]
            original_line = info["original"]

            if name not in remote_reqs:
                # Missing on remote
                to_install.append(original_line + "\n")
            else:
                remote_ver = remote_reqs[name]["version"]
                # If local has version, compare.
                if local_ver and remote_ver:
                    if local_ver != remote_ver:
                        # Version mismatch
                        to_install.append(original_line + "\n")
                # If local has no version, strict existence is enough (already checked)

        return to_install

    def compute_requirements_hash(self, req_lines):
        """
        Compute a hash of the requirements file content.
        This hash can be used to detect if the virtualenv needs to be recreated.

        Args:
            req_lines: List of requirement lines (strings)

        Returns:
            str: SHA256 hash of sorted requirements (hexdigest)
        """
        # Normalize requirements: sort and strip whitespace
        normalized = sorted(
            [
                line.strip()
                for line in req_lines
                if line.strip() and not line.strip().startswith("#")
            ]
        )
        content = "\n".join(normalized).encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def get_stored_venv_hash(self):
        """
        Get the stored virtualenv hash from cache.

        Returns:
            str or None: The stored hash if it exists, None otherwise
        """
        if not os.path.exists(self.venv_hash_file):
            return None
        with open(self.venv_hash_file, "r") as f:
            return f.read().strip()

    def store_venv_hash(self, req_hash):
        """
        Store the virtualenv hash to cache.

        Args:
            req_hash: The hash to store
        """
        with open(self.venv_hash_file, "w") as f:
            f.write(req_hash)

    def should_recreate_venv(self, req_lines):
        """
        Check if the virtualenv should be recreated based on requirements hash.

        Args:
            req_lines: List of requirement lines (strings)

        Returns:
            bool: True if venv should be recreated, False if it can be reused
        """
        current_hash = self.compute_requirements_hash(req_lines)
        stored_hash = self.get_stored_venv_hash()

        if stored_hash is None:
            # No hash stored, venv should be created/recreated
            return True

        if current_hash != stored_hash:
            # Hash mismatch, requirements changed, venv needs recreation
            if self.logger:
                self.logger.info(
                    f"Requirements changed (hash mismatch), venv will be recreated."
                )
            return True

        # Hash matches, venv can be reused
        if self.logger:
            self.logger.info(
                f"Requirements unchanged (hash matches), reusing existing venv."
            )
        return False

    def get_stored_env_hash(self):
        """
        Get the stored environment hash from cache.

        Returns:
            str or None: The stored hash if it exists, None otherwise
        """
        if not os.path.exists(self.env_hash_file):
            return None
        with open(self.env_hash_file, "r") as f:
            return f.read().strip()

    def store_env_hash(self, env_hash):
        """
        Store the environment hash to cache.

        Args:
            env_hash: The hash to store
        """
        with open(self.env_hash_file, "w") as f:
            f.write(env_hash)


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
        logger: logging.Logger = None,
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
            local_socket._closed = False  # Track if server is closed
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
                except Exception as e:
                    # Silently ignore connection errors when tunnel is closing
                    if self.forward_server and not self.forward_server._closed:
                        # Only log if server is still supposed to be running
                        pass
                finally:
                    try:
                        client_socket.close()
                    except Exception:
                        pass

            def accept_handler():
                while True:
                    try:
                        # Check if server is closed before accepting
                        if (
                            hasattr(self.forward_server, "_closed")
                            and self.forward_server._closed
                        ):
                            break
                        client_socket, addr = self.forward_server.accept()
                        thread = threading.Thread(
                            target=forward_handler,
                            args=(client_socket,),
                            daemon=True,
                        )
                        thread.start()
                    except (OSError, socket.error):
                        # Socket closed or connection refused - normal when shutting down
                        break
                    except Exception:
                        break

            forward_thread = threading.Thread(target=accept_handler, daemon=True)
            forward_thread.start()

            msg = f"🎉 Dashboard forwarded and available here : http://localhost:{self.local_port}"
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
                # Mark server as closed first to prevent new connections
                self.forward_server._closed = True
                self.forward_server.close()
            except Exception:
                pass
        if self.ssh_client:
            try:
                self.ssh_client.close()
            except Exception:
                pass
        return False
