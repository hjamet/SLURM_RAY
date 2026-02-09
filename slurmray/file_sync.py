"""
File synchronization manager for local packages.
Handles hash computation, comparison, and incremental upload.
"""

import os
import json
import hashlib
import logging
import tempfile
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
        
        Optimized: uses local cache to avoid recomputing hashes for unchanged files.
        """
        hashes = {}
        files_to_process = set()  # Use set to avoid duplicates
        
        # Load previous local hashes to optimize computation
        previous_hashes = self.load_local_hashes()
        
        for file_path in file_paths:
            # Convert to absolute path
            if not os.path.isabs(file_path):
                abs_path = os.path.join(self.project_root, file_path)
            else:
                abs_path = file_path
            
            # Resolve symlinks and normalize
            abs_path = os.path.realpath(abs_path)

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
                
                # Performance Optimization: Check mtime and size before recomputing hash
                stat = os.stat(abs_path)
                prev_info = previous_hashes.get(rel_path)
                
                if (prev_info and 
                    prev_info.get("mtime") == stat.st_mtime and 
                    prev_info.get("size") == stat.st_size and
                    prev_info.get("hash")):
                    # File likely unchanged, reuse hash
                    hashes[rel_path] = prev_info
                    continue

                # Compute hash and metadata
                file_hash = self.compute_file_hash(abs_path)
                if file_hash:
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
    ) -> Tuple[List[str], List[str], int]:
        """
        Compare local and remote hashes to determine which files need uploading
        and which remote files should be deleted (renamed/removed locally).
        Returns (files_to_upload, files_to_delete, total_tracked_count).
        """
        if remote_hashes is None:
            remote_hashes = self.hash_manager.load_remote_hashes()

        # Compute current local hashes
        local_hashes = self.hash_manager.compute_hashes(local_files)

        # Compare hashes: detect new and modified files
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

        # Detect files that exist remotely but not locally (renamed/deleted)
        files_to_delete = []
        for rel_path in remote_hashes:
            if rel_path not in local_hashes:
                files_to_delete.append(rel_path)
                if self.logger:
                    self.logger.debug(f"File deleted locally: {rel_path}")

        # Save updated local hashes
        self.hash_manager.save_local_hashes(local_hashes)

        return files_to_upload, files_to_delete, len(local_hashes)

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

    def cleanup_remote_hashes(
        self,
        deleted_files: List[str],
        remote_hashes: Dict[str, Dict[str, any]] = None,
    ):
        """
        Remove deleted files from remote hash cache.
        """
        if remote_hashes is None:
            remote_hashes = self.hash_manager.load_remote_hashes()

        for rel_path in deleted_files:
            remote_hashes.pop(rel_path, None)

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

    def verify_remote_hashes_existence(
        self, ssh_client, remote_base_dir: str, remote_hashes: Dict[str, Dict[str, any]]
    ) -> Dict[str, Dict[str, any]]:
        """
        Verify that files in remote_hashes actually exist on the server.
        Removes entries for files that are missing.
        Uses a single find command for efficiency.
        """
        if not remote_hashes:
            return {}

        try:
            # Use find to list all files in project root (excluding .venv and .slogs)
            # This is much faster than individual stat calls
            cmd = (
                f"find '{remote_base_dir}' -type f "
                f"! -path '*/.venv/*' ! -path '*/.slogs/*' "
                f"-printf '%P\\n'"
            )
            stdin, stdout, stderr = ssh_client.exec_command(cmd)
            
            existing_files = set()
            for line in stdout:
                file_rel = line.strip()
                if file_rel:
                    existing_files.add(file_rel)
            
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                # If find fails, we don't prune anything to be safe
                return remote_hashes

            # Keep only items that still exist on server
            pruned_hashes = {}
            removed_count = 0
            for rel_path, info in remote_hashes.items():
                if rel_path in existing_files:
                    pruned_hashes[rel_path] = info
                else:
                    removed_count += 1
            
            if removed_count > 0 and self.logger:
                self.logger.info(
                    f"Found {removed_count} missing files on cluster. Cache invalidated for these files."
                )
            
            return pruned_hashes

        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to verify remote files existence: {e}")
            return remote_hashes

    def save_remote_hashes_to_server(
        self, ssh_client, remote_hash_file_path: str, hashes: Dict[str, Dict[str, any]]
    ):
        """
        Save remote file hashes to the server via SFTP.
        Uses SFTP put instead of heredoc to avoid truncation on large payloads.
        """
        local_tmp = None
        try:
            # Create JSON content
            content = json.dumps(hashes, indent=2)
            content_bytes = content.encode("utf-8")

            # Write to local temp file first
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".json", delete=False
            ) as tmp:
                tmp.write(content_bytes)
                local_tmp = tmp.name

            # Ensure remote directory exists
            remote_dir = os.path.dirname(remote_hash_file_path)
            stdin, stdout, stderr = ssh_client.exec_command(
                f"mkdir -p '{remote_dir}'"
            )
            stdout.channel.recv_exit_status()

            # Upload via SFTP (robust against large payloads)
            sftp = ssh_client.open_sftp()
            try:
                sftp.put(local_tmp, remote_hash_file_path)

                # Verify file size matches
                remote_stat = sftp.stat(remote_hash_file_path)
                if remote_stat.st_size != len(content_bytes):
                    if self.logger:
                        self.logger.warning(
                            f"⚠️ Hash file size mismatch! "
                            f"Expected: {len(content_bytes)} bytes, "
                            f"Remote: {remote_stat.st_size} bytes. "
                            f"File sync may be unreliable."
                        )
                else:
                    if self.logger:
                        self.logger.debug(
                            f"Hash file saved: {len(hashes)} entries, "
                            f"{len(content_bytes)} bytes"
                        )
            finally:
                sftp.close()

        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to save remote hashes to server: {e}")
        finally:
            if local_tmp and os.path.exists(local_tmp):
                os.unlink(local_tmp)

