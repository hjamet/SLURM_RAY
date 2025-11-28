import os
import sys
import time
import paramiko
import subprocess
import logging
from getpass import getpass
from typing import Any, Optional

from slurmray.backend.base import ClusterBackend

class RemoteMixin(ClusterBackend):
    """Mixin for remote execution via SSH"""
    
    def __init__(self, launcher):
        super().__init__(launcher)
        self.ssh_client = None
        self.job_id = None

    def _connect(self):
        """Establish SSH connection"""
        if self.ssh_client and self.ssh_client.get_transport() and self.ssh_client.get_transport().is_active():
            return

        connected = False
        self.logger.info("Connecting to the remote server...")
        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        while not connected:
            try:
                if self.launcher.server_password is None:
                    # Try loading from env if available, otherwise prompt
                    # Only use generic env vars if specific ones aren't set or if logic dictates
                    # Check if password was passed in __init__ (already handled by launcher init)
                    
                    # Explicitly check for DESI_PASSWORD if cluster is desi
                    if hasattr(self.launcher, 'cluster_type') and self.launcher.cluster_type == 'desi':
                         env_pass = os.environ.get("DESI_PASSWORD")
                         if env_pass:
                             self.launcher.server_password = env_pass

                    if self.launcher.server_password is None:
                        # Add ssh key support? Assuming password for now as per original code
                        try:
                            self.launcher.server_password = getpass("Enter your cluster password: ")
                        except Exception:
                            # Handle case where getpass fails (e.g. non-interactive terminal)
                            pass

                if self.launcher.server_password is None:
                     raise ValueError("No password provided and cannot prompt (non-interactive)")

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
                     raise # Fail fast if non-interactive

    def _push_file(
        self, file_path: str, sftp: paramiko.SFTPClient, remote_base_dir: str
    ):
        """Push a file to the remote server"""
        self.logger.info(f"Pushing file {os.path.basename(file_path)} to the remote server...")

        # Determine the path to the file
        local_path = file_path
        local_path_from_pwd = os.path.relpath(local_path, self.launcher.pwd_path)
        remote_path = os.path.join(
            remote_base_dir, local_path_from_pwd
        )

        # Create the directory if not exists
        stdin, stdout, stderr = self.ssh_client.exec_command(
            f"mkdir -p '{os.path.dirname(remote_path)}'"
        )
        # Wait for command to finish
        stdout.channel.recv_exit_status()
        
        # Copy the file to the server
        sftp.put(file_path, remote_path)
