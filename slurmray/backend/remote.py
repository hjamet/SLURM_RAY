import os
import sys
import time
import paramiko
import subprocess
import logging
from getpass import getpass
from typing import Any, Optional, List

from slurmray.backend.base import ClusterBackend


class RemoteMixin(ClusterBackend):
    """Mixin for remote execution via SSH"""

    def __init__(self, launcher):
        super().__init__(launcher)
        self.ssh_client = None
        self.job_id = None
        self._sftp_client = None

    def _connect(self):
        """Establish SSH connection"""
        if (
            self.ssh_client
            and self.ssh_client.get_transport()
            and self.ssh_client.get_transport().is_active()
        ):
            return

        connected = False
        self.logger.info("Connecting to the remote server...")
        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._sftp_client = None  # Reset SFTP client on new connection

        while not connected:
            try:
                if self.launcher.server_password is None:
                    # Password not provided: prompt interactively
                    # (Credentials from .env or explicit parameters are already loaded in RayLauncher.__init__)
                    try:
                        self.launcher.server_password = getpass(
                            "Enter your cluster password: "
                        )
                    except Exception:
                        # Handle case where getpass fails (e.g. non-interactive terminal)
                        pass

                if self.launcher.server_password is None:
                    raise ValueError(
                        "No password provided and cannot prompt (non-interactive)"
                    )

                self.ssh_client.connect(
                    hostname=self.launcher.server_ssh,
                    username=self.launcher.server_username,
                    password=self.launcher.server_password,
                )
                connected = True
            except paramiko.ssh_exception.AuthenticationException:
                self.launcher.server_password = None
                self.logger.warning("Wrong password, please try again.")
                # Only retry interactively if we failed
                if not sys.stdin.isatty():
                    raise  # Fail fast if non-interactive

    def get_sftp(self):
        """Get or create cached SFTP client"""
        if self._sftp_client is None:
            self._connect()
            self._sftp_client = self.ssh_client.open_sftp()
        else:
            # Check if connection is still active
            try:
                self._sftp_client.listdir(".")
            except (OSError, EOFError):
                 # Reconnect
                 if self._sftp_client:
                     try:
                         self._sftp_client.close()
                     except:
                         pass
                 self._connect()
                 self._sftp_client = self.ssh_client.open_sftp()
        return self._sftp_client

    def _push_file(
        self, file_path: str, sftp: paramiko.SFTPClient, remote_base_dir: str
    ):
        """Push a file to the remote server"""
        self.logger.info(
            f"Pushing file {os.path.basename(file_path)} to the remote server..."
        )

        # Determine the path to the file
        local_path = file_path
        if not os.path.isabs(local_path):
            local_path = os.path.join(self.launcher.pwd_path, local_path)
        local_path = os.path.abspath(local_path)

        local_path_from_pwd = os.path.relpath(local_path, self.launcher.pwd_path)
        remote_path = os.path.join(remote_base_dir, local_path_from_pwd)

        # Create the directory if not exists
        stdin, stdout, stderr = self.ssh_client.exec_command(
            f"mkdir -p '{os.path.dirname(remote_path)}'"
        )
        # Wait for command to finish
        stdout.channel.recv_exit_status()

        # Copy the file to the server
        sftp.put(local_path, remote_path)

    def _push_file_wrapper(
        self,
        rel_path: str,
        sftp: paramiko.SFTPClient,
        remote_base_dir: str,
        ssh_client: paramiko.SSHClient = None,
    ):
        """
        Wrapper to call _push_file with the correct signature for each backend.
        """
        import inspect

        # Get the signature of _push_file for this backend
        sig = inspect.signature(self._push_file)
        param_count = len(sig.parameters)

        if param_count == 4:  # SlurmBackend: (self, file_path, sftp, ssh_client)
            if ssh_client is None:
                ssh_client = self.ssh_client
            self._push_file(rel_path, sftp, ssh_client)
        else:  # RemoteMixin/DesiBackend: (self, file_path, sftp, remote_base_dir)
            self._push_file(rel_path, sftp, remote_base_dir)

    def _sync_local_files_incremental(
        self,
        sftp: paramiko.SFTPClient,
        remote_base_dir: str,
        local_files: List[str],
        ssh_client: paramiko.SSHClient = None,
    ):
        """
        Synchronize local files incrementally using hash comparison.
        Only uploads files that have changed.
        """
        from slurmray.file_sync import FileHashManager, LocalFileSyncManager

        # Use provided ssh_client or self.ssh_client
        if ssh_client is None:
            ssh_client = self.ssh_client

        # Initialize sync manager
        hash_manager = FileHashManager(self.launcher.pwd_path, self.logger)
        sync_manager = LocalFileSyncManager(
            self.launcher.pwd_path, hash_manager, self.logger
        )

        # Remote hash file path
        remote_hash_file = os.path.join(
            remote_base_dir, ".slogs", ".remote_file_hashes.json"
        )

        # Fetch remote hashes
        remote_hashes = sync_manager.fetch_remote_hashes(ssh_client, remote_hash_file)

        # Determine which files need uploading
        files_to_upload = sync_manager.get_files_to_upload(local_files, remote_hashes)

        if not files_to_upload:
            self.logger.info("✅ All local files are up to date, no upload needed.")
            return

        self.logger.info(
            f"📤 Uploading {len(files_to_upload)} modified/new file(s) out of {len(local_files)} total..."
        )

        # Upload files
        uploaded_files = []
        for rel_path in files_to_upload:
            # Convert relative path to absolute
            abs_path = os.path.join(self.launcher.pwd_path, rel_path)

            # Handle directories (packages)
            if os.path.isdir(abs_path):
                # Upload all Python files in the directory recursively
                for root, dirs, files in os.walk(abs_path):
                    # Skip __pycache__
                    dirs[:] = [d for d in dirs if d != "__pycache__"]
                    for file in files:
                        if file.endswith(".py"):
                            file_path = os.path.join(root, file)
                            file_rel = os.path.relpath(
                                file_path, self.launcher.pwd_path
                            )
                            self._push_file_wrapper(
                                file_rel, sftp, remote_base_dir, ssh_client
                            )
                            uploaded_files.append(file_rel)
            else:
                # Single file
                self._push_file_wrapper(rel_path, sftp, remote_base_dir, ssh_client)
                uploaded_files.append(rel_path)

        # Update remote hashes after successful upload
        sync_manager.update_remote_hashes(uploaded_files, remote_hashes)
        sync_manager.save_remote_hashes_to_server(
            ssh_client, remote_hash_file, remote_hashes
        )

        self.logger.info(f"✅ Successfully uploaded {len(uploaded_files)} file(s).")
