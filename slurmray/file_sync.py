"""
File synchronization manager for local packages.
Handles hash computation, comparison, and incremental upload.
"""

import os
import json
import hashlib
import logging
from typing import Dict, Set, List, Tuple
from pathlib import Path


class FileHashManager:
    """Manages file hashes for synchronization."""

    def __init__(self, project_root: str, logger: logging.Logger = None):
        self.project_root = os.path.abspath(project_root)
        self.logger = logger or logging.getLogger(__name__)
        self.cache_dir = os.path.join(self.project_root, ".slogs")
        self.local_hash_file = os.path.join(self.cache_dir, ".local_file_hashes.json")
        self.remote_hash_file = os.path.join(
            self.cache_dir, ".remote_file_hashes.json"
        )

        # Ensure cache directory exists
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def compute_file_hash(self, file_path: str) -> str:
        """Compute SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                # Read file in chunks to handle large files
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to compute hash for {file_path}: {e}")
            return ""

    def compute_hashes(self, file_paths: List[str]) -> Dict[str, Dict[str, any]]:
        """
        Compute hashes for multiple files and directories.
        For directories, recursively computes hashes for all files within.
        Returns dict: {rel_path: {"hash": "...", "mtime": ..., "size": ...}}
        """
        hashes = {}
        files_to_process = set()  # Use set to avoid duplicates
        
        for file_path in file_paths:
            # Convert to absolute path
            if not os.path.isabs(file_path):
                abs_path = os.path.join(self.project_root, file_path)
            else:
                abs_path = file_path

            if not os.path.exists(abs_path):
                continue

            # Get relative path
            try:
                rel_path = os.path.relpath(abs_path, self.project_root)
            except ValueError:
                continue

            # Skip if outside project
            if rel_path.startswith(".."):
                continue

            # If it's a directory, recursively collect all files
            if os.path.isdir(abs_path):
                for root, dirs, files in os.walk(abs_path):
                    # Skip __pycache__ directories
                    dirs[:] = [d for d in dirs if d != "__pycache__"]
                    for file in files:
                        file_abs_path = os.path.join(root, file)
                        try:
                            file_rel_path = os.path.relpath(file_abs_path, self.project_root)
                            # Skip if outside project
                            if not file_rel_path.startswith(".."):
                                files_to_process.add(file_abs_path)
                        except ValueError:
                            continue
            else:
                # It's a file, add it directly
                files_to_process.add(abs_path)

        # Compute hashes for all collected files
        for abs_path in files_to_process:
            try:
                rel_path = os.path.relpath(abs_path, self.project_root)
                # Skip if outside project (double check)
                if rel_path.startswith(".."):
                    continue
                
                # Compute hash and metadata
                file_hash = self.compute_file_hash(abs_path)
                if file_hash:
                    stat = os.stat(abs_path)
                    hashes[rel_path] = {
                        "hash": file_hash,
                        "mtime": stat.st_mtime,
                        "size": stat.st_size,
                    }
            except Exception as e:
                if self.logger:
                    self.logger.debug(f"Skipping file {abs_path}: {e}")
                continue

        return hashes

    def load_local_hashes(self) -> Dict[str, Dict[str, any]]:
        """Load local file hashes from cache."""
        if not os.path.exists(self.local_hash_file):
            return {}
        try:
            with open(self.local_hash_file, "r") as f:
                return json.load(f)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to load local hashes: {e}")
            return {}

    def save_local_hashes(self, hashes: Dict[str, Dict[str, any]]):
        """Save local file hashes to cache."""
        try:
            with open(self.local_hash_file, "w") as f:
                json.dump(hashes, f, indent=2)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to save local hashes: {e}")

    def load_remote_hashes(self) -> Dict[str, Dict[str, any]]:
        """Load remote file hashes from cache."""
        if not os.path.exists(self.remote_hash_file):
            return {}
        try:
            with open(self.remote_hash_file, "r") as f:
                return json.load(f)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to load remote hashes: {e}")
            return {}

    def save_remote_hashes(self, hashes: Dict[str, Dict[str, any]]):
        """Save remote file hashes to cache."""
        try:
            with open(self.remote_hash_file, "w") as f:
                json.dump(hashes, f, indent=2)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to save remote hashes: {e}")


class LocalFileSyncManager:
    """Manages incremental synchronization of local files."""

    def __init__(
        self,
        project_root: str,
        hash_manager: FileHashManager,
        logger: logging.Logger = None,
    ):
        self.project_root = os.path.abspath(project_root)
        self.hash_manager = hash_manager
        self.logger = logger or logging.getLogger(__name__)

    def get_files_to_upload(
        self, local_files: List[str], remote_hashes: Dict[str, Dict[str, any]] = None
    ) -> List[str]:
        """
        Compare local and remote hashes to determine which files need uploading.
        Returns list of relative paths to files that need uploading.
        """
        if remote_hashes is None:
            remote_hashes = self.hash_manager.load_remote_hashes()

        # Compute current local hashes
        local_hashes = self.hash_manager.compute_hashes(local_files)

        # Compare hashes
        files_to_upload = []
        for rel_path, local_info in local_hashes.items():
            remote_info = remote_hashes.get(rel_path)

            # File needs upload if:
            # 1. Not present remotely
            # 2. Hash differs
            if remote_info is None:
                files_to_upload.append(rel_path)
                if self.logger:
                    self.logger.debug(f"New file detected: {rel_path}")
            elif remote_info.get("hash") != local_info["hash"]:
                files_to_upload.append(rel_path)
                if self.logger:
                    self.logger.debug(f"File modified: {rel_path} (hash changed)")

        # Save updated local hashes
        self.hash_manager.save_local_hashes(local_hashes)

        return files_to_upload

    def update_remote_hashes(
        self,
        uploaded_files: List[str],
        remote_hashes: Dict[str, Dict[str, any]] = None,
    ):
        """
        Update remote hash cache after successful upload.
        """
        if remote_hashes is None:
            remote_hashes = self.hash_manager.load_remote_hashes()

        # Get current local hashes for uploaded files
        local_hashes = self.hash_manager.compute_hashes(uploaded_files)

        # Update remote hashes with local hashes
        for rel_path in uploaded_files:
            if rel_path in local_hashes:
                remote_hashes[rel_path] = local_hashes[rel_path]

        # Save updated remote hashes
        self.hash_manager.save_remote_hashes(remote_hashes)

    def fetch_remote_hashes(self, ssh_client, remote_hash_file_path: str) -> Dict[str, Dict[str, any]]:
        """
        Fetch remote file hashes from the server via SSH.
        Returns dict of remote hashes or empty dict if file doesn't exist.
        """
        try:
            stdin, stdout, stderr = ssh_client.exec_command(
                f"cat '{remote_hash_file_path}' 2>/dev/null || echo '{{}}'"
            )
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0:
                content = stdout.read().decode("utf-8").strip()
                if content:
                    return json.loads(content)
        except Exception as e:
            if self.logger:
                self.logger.debug(f"Could not fetch remote hashes: {e}")
        return {}

    def save_remote_hashes_to_server(
        self, ssh_client, remote_hash_file_path: str, hashes: Dict[str, Dict[str, any]]
    ):
        """Save remote file hashes to the server via SSH."""
        try:
            # Create JSON content
            content = json.dumps(hashes, indent=2)

            # Write to temporary file first, then move (atomic operation)
            temp_path = remote_hash_file_path + ".tmp"
            stdin, stdout, stderr = ssh_client.exec_command(
                f"mkdir -p '{os.path.dirname(remote_hash_file_path)}'"
            )
            stdout.channel.recv_exit_status()

            # Write content via echo (simple but works)
            stdin, stdout, stderr = ssh_client.exec_command(
                f"cat > '{temp_path}' << 'EOF'\n{content}\nEOF"
            )
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0:
                # Move temp file to final location
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"mv '{temp_path}' '{remote_hash_file_path}'"
                )
                stdout.channel.recv_exit_status()
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to save remote hashes to server: {e}")

