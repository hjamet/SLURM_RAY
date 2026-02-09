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

