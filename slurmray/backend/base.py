from abc import ABC, abstractmethod
from typing import Any, Dict
import os
import subprocess
import sys

class ClusterBackend(ABC):
    """Abstract base class for cluster backends"""

    def __init__(self, launcher):
        """
        Initialize the backend.
        
        Args:
            launcher: The RayLauncher instance containing configuration
        """
        self.launcher = launcher
        self.logger = launcher.logger

    @abstractmethod
    def run(self, cancel_old_jobs: bool = True) -> Any:
        """
        Run the job on the backend.
        
        Args:
            cancel_old_jobs (bool): Whether to cancel old jobs before running
            
        Returns:
            Any: The result of the execution
        """
        pass

    @abstractmethod
    def cancel(self, job_id: str):
        """
        Cancel a running job.
        
        Args:
            job_id (str): The ID of the job to cancel
        """
        pass

    def _generate_requirements(self, force_regenerate=False):
        """
        Generate requirements.txt.
        
        Args:
            force_regenerate: If True, always regenerate. If False, check if dependencies changed.
        """
        from slurmray.utils import DependencyManager
        
        req_file = os.path.join(self.launcher.project_path, "requirements.txt")
        dep_manager = DependencyManager(self.launcher.project_path, self.logger)
        
        # Check if we should skip regeneration
        if not force_regenerate and os.path.exists(req_file):
            # Get current environment packages hash
            result = subprocess.run(
                ["pip-chill"],
                capture_output=True,
                text=True,
                shell=True
            )
            if result.returncode == 0:
                current_env_lines = result.stdout.strip().split('\n')
                current_env_hash = dep_manager.compute_requirements_hash(current_env_lines)
                
                # Check stored environment hash
                stored_env_hash = dep_manager.get_stored_env_hash()
                if stored_env_hash == current_env_hash:
                    # Environment hasn't changed, requirements.txt should be up to date
                    if self.logger:
                        self.logger.info("Environment unchanged, requirements.txt is up to date, skipping regeneration.")
                    return
        
        # Generate requirements.txt
        if self.logger:
            self.logger.info("Generating requirements.txt...")
        
        # Use pip-chill with versions to allow smart comparison
        subprocess.run(
            [f"pip-chill > {self.launcher.project_path}/requirements.txt"],
            shell=True,
        )
        
        import dill
        dill_version = dill.__version__
        
        with open(f"{self.launcher.project_path}/requirements.txt", "r") as file:
            lines = file.readlines()
            # Filter out slurmray, ray and dill
            lines = [line for line in lines if "slurmray" not in line and "ray" not in line and "dill" not in line]
            
            # Add pinned dill version to ensure serialization compatibility
            lines.append(f"dill=={dill_version}\n")
            
            # Add ray[default] without pinning version (to allow best compatible on remote)
            lines.append("ray[default]\n")
            
            # Ensure torch is present (common dependency)
            if not any("torch" in line for line in lines):
                lines.append("torch\n")
                
        with open(f"{self.launcher.project_path}/requirements.txt", "w") as file:
            file.writelines(lines)
        
        # Store hash of environment for future checks
        result = subprocess.run(
            ["pip-chill"],
            capture_output=True,
            text=True,
            shell=True
        )
        if result.returncode == 0:
            env_lines = result.stdout.strip().split('\n')
            env_hash = dep_manager.compute_requirements_hash(env_lines)
            dep_manager.store_env_hash(env_hash)

    def _optimize_requirements(self, ssh_client, venv_command_prefix=""):
        """
        Optimize requirements by comparing local and remote installed packages.
        Returns path to the optimized requirements file (requirements_to_install.txt).
        """
        from slurmray.utils import DependencyManager
        
        dep_manager = DependencyManager(self.launcher.project_path, self.logger)
        req_file = os.path.join(self.launcher.project_path, "requirements.txt")
        
        if not os.path.exists(req_file):
            return req_file
            
        with open(req_file, 'r') as f:
            local_reqs_lines = f.readlines()
            
        cache_lines = dep_manager.load_cache()
        remote_lines = []
        
        # Only skip remote check if cache is non-empty
        if cache_lines:
            self.logger.info("Using cached requirements list.")
            remote_lines = cache_lines
        else:
            self.logger.info("Scanning remote packages (no cache found)...")
            cmd = f"{venv_command_prefix} pip list --format=freeze"
            try:
                stdin, stdout, stderr = ssh_client.exec_command(cmd)
                exit_status = stdout.channel.recv_exit_status()
                if exit_status == 0:
                    remote_lines = [l + "\n" for l in stdout.read().decode('utf-8').splitlines()]
                    dep_manager.save_cache(remote_lines)
                else:
                    # If pip list fails (e.g. venv not active or created), we assume empty
                    self.logger.warning("Remote pip list failed (venv might not exist).")
            except Exception as e:
                self.logger.warning(f"Failed to scan remote: {e}")
        
        # Compare
        to_install = dep_manager.compare(local_reqs_lines, remote_lines)
        
        # Write delta file
        delta_file = os.path.join(self.launcher.project_path, "requirements_to_install.txt")
        with open(delta_file, 'w') as f:
            f.writelines(to_install)
            
        self.logger.info(f"Optimization: {len(to_install)} packages to install.")
        return delta_file

    def _check_python_version_compatibility(self, ssh_client=None):
        """
        Check Python version compatibility between local and remote environments.
        Warns if there are significant version differences.
        
        Args:
            ssh_client: Optional SSH client for remote version check. If None, only logs local version.
        """
        local_version = sys.version_info
        local_version_str = f"{local_version.major}.{local_version.minor}.{local_version.micro}"
        
        if self.logger:
            self.logger.info(f"Local Python version: {local_version_str}")
        
        if ssh_client:
            # Check remote Python version
            try:
                stdin, stdout, stderr = ssh_client.exec_command("python3 --version")
                remote_version_output = stdout.read().decode('utf-8').strip()
                if remote_version_output:
                    # Extract version from "Python X.Y.Z"
                    import re
                    match = re.search(r'(\d+)\.(\d+)\.(\d+)', remote_version_output)
                    if match:
                        remote_major = int(match.group(1))
                        remote_minor = int(match.group(2))
                        remote_micro = int(match.group(3))
                        
                        if self.logger:
                            self.logger.info(f"Remote Python version: {remote_version_output}")
                        
                        # Check for significant version differences
                        if local_version.major != remote_major:
                            if self.logger:
                                self.logger.warning(
                                    f"Python major version mismatch: local={local_version.major}, remote={remote_major}. "
                                    f"This may cause compatibility issues. SlurmRay uses source-based serialization "
                                    f"to mitigate this, but some issues may still occur."
                                )
                        elif local_version.minor != remote_minor:
                            if self.logger:
                                self.logger.info(
                                    f"Python minor version difference: local={local_version.major}.{local_version.minor}, "
                                    f"remote={remote_major}.{remote_minor}. This should generally be fine with "
                                    f"source-based serialization."
                                )
                        else:
                            if self.logger:
                                self.logger.info("Python versions are compatible.")
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Could not check remote Python version: {e}")
