#!/usr/bin/env python3
"""
Cleanup script for old SlurmRay projects on cluster.

This script is designed to be run as a cron job to automatically remove
old project files and venv that have exceeded their retention period.

Usage:
    python cleanup_old_projects.py [--cluster-type slurm|desi] [--base-path /path/to/users]

The script will:
- Scan user directories for slurmray-server/{project_name}/ directories
- Read .retention_timestamp and .retention_days files
- Delete projects that have exceeded their retention period
"""

import os
import sys
import time
import argparse
import logging
from pathlib import Path


def read_retention_files(project_dir):
    """
    Read retention timestamp and days from project directory.
    
    Args:
        project_dir: Path to project directory
        
    Returns:
        tuple: (timestamp, retention_days) or (None, None) if files don't exist
    """
    timestamp_file = os.path.join(project_dir, ".retention_timestamp")
    retention_days_file = os.path.join(project_dir, ".retention_days")
    
    if not os.path.exists(timestamp_file) or not os.path.exists(retention_days_file):
        return None, None
    
    try:
        with open(timestamp_file, 'r') as f:
            timestamp_str = f.read().strip()
            timestamp = int(timestamp_str)
        
        with open(retention_days_file, 'r') as f:
            retention_days_str = f.read().strip()
            retention_days = int(retention_days_str)
        
        return timestamp, retention_days
    except (ValueError, IOError):
        return None, None


def cleanup_user_projects(username, base_path, cluster_type, logger):
    """
    Cleanup old projects for a specific user.
    
    Args:
        username: Username
        base_path: Base path to user directories (e.g., /users or /home)
        cluster_type: Type of cluster ('slurm' or 'desi')
        logger: Logger instance
    """
    user_dir = os.path.join(base_path, username)
    if not os.path.exists(user_dir):
        return
    
    slurmray_base = os.path.join(user_dir, "slurmray-server")
    if not os.path.exists(slurmray_base):
        return
    
    # Scan for project directories
    if not os.path.isdir(slurmray_base):
        return
    
    for item in os.listdir(slurmray_base):
        project_dir = os.path.join(slurmray_base, item)
        if not os.path.isdir(project_dir):
            continue
        
        # Read retention files
        timestamp, retention_days = read_retention_files(project_dir)
        
        if timestamp is None or retention_days is None:
            # No retention files, skip this project
            continue
        
        # Calculate age in days
        current_time = int(time.time())
        age_seconds = current_time - timestamp
        age_days = age_seconds / (24 * 3600)
        
        # Check if project should be deleted
        if age_days > retention_days:
            logger.info(f"Deleting project {username}/{item}: age={age_days:.1f} days, retention={retention_days} days")
            try:
                import shutil
                shutil.rmtree(project_dir)
                logger.info(f"Successfully deleted project {username}/{item}")
            except Exception as e:
                logger.error(f"Failed to delete project {username}/{item}: {e}")
                raise  # Fail-fast on errors


def main():
    """Main entry point for cleanup script"""
    parser = argparse.ArgumentParser(description="Cleanup old SlurmRay projects on cluster")
    parser.add_argument(
        "--cluster-type",
        choices=["slurm", "desi"],
        default="slurm",
        help="Type of cluster (default: slurm)"
    )
    parser.add_argument(
        "--base-path",
        help="Base path to user directories (default: /users for slurm, /home for desi)"
    )
    parser.add_argument(
        "--log-file",
        help="Log file path (default: /tmp/slurmray_cleanup.log)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_file = args.log_file or "/tmp/slurmray_cleanup.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)
    
    # Determine base path
    if args.base_path:
        base_path = args.base_path
    else:
        if args.cluster_type == "slurm":
            base_path = "/users"
        else:  # desi
            base_path = "/home"
    
    logger.info(f"Starting cleanup for cluster type: {args.cluster_type}, base path: {base_path}")
    
    if not os.path.exists(base_path):
        logger.error(f"Base path does not exist: {base_path}")
        sys.exit(1)
    
    # Scan all user directories
    cleaned_count = 0
    for username in os.listdir(base_path):
        user_path = os.path.join(base_path, username)
        if not os.path.isdir(user_path):
            continue
        
        try:
            cleanup_user_projects(username, base_path, args.cluster_type, logger)
        except Exception as e:
            logger.error(f"Error processing user {username}: {e}")
            raise  # Fail-fast on errors
    
    logger.info("Cleanup completed")


if __name__ == "__main__":
    main()

