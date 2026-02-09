"""
File synchronization for local packages — Mirror Mode.
Lists local files and remote files for full mirror sync.
No hash caching: always uploads everything, deletes orphans.
"""

import os
import logging
from typing import Set, List


def list_local_files(project_root: str, file_paths: List[str], logger: logging.Logger = None) -> Set[str]:
    """
    Walk local directories and individual files to produce a set of
    relative paths (from project_root) that should exist on the remote.

    Skips __pycache__ directories.

    Args:
        project_root: Absolute path to the project root.
        file_paths:   List of relative paths to files or directories to include.
        logger:       Optional logger instance.

    Returns:
        Set of relative file paths.
    """
    project_root = os.path.abspath(project_root)
    result: Set[str] = set()

    for entry in file_paths:
        abs_entry = os.path.join(project_root, entry)

        if not os.path.exists(abs_entry):
            if logger:
                logger.debug(f"Skipping non-existent path: {entry}")
            continue

        if os.path.isfile(abs_entry):
            result.add(entry)
        elif os.path.isdir(abs_entry):
            for root, dirs, files in os.walk(abs_entry):
                # Skip __pycache__
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fname in files:
                    abs_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(abs_path, project_root)
                    result.add(rel_path)

    return result


def list_remote_files(ssh_client, remote_base_dir: str, logger: logging.Logger = None) -> Set[str]:
    """
    List all files on the remote server under remote_base_dir.
    Excludes .venv/, .slogs/, __pycache__/, and venv/ directories.

    Args:
        ssh_client:      Paramiko SSH client.
        remote_base_dir: Absolute path on the server.
        logger:          Optional logger instance.

    Returns:
        Set of relative file paths (from remote_base_dir).
    """
    cmd = (
        f"find '{remote_base_dir}' -type f "
        f"! -path '*/.venv/*' ! -path '*/.slogs/*' "
        f"! -path '*/venv/*' ! -path '*/__pycache__/*' "
        f"-printf '%P\\n'"
    )

    try:
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            if logger:
                logger.debug(f"Remote find returned exit status {exit_status}")
            return set()

        output = stdout.read().decode("utf-8", errors="replace").strip()
        if not output:
            return set()

        return {line for line in output.splitlines() if line}

    except Exception as e:
        if logger:
            logger.warning(f"Failed to list remote files: {e}")
        return set()
