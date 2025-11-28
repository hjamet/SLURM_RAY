from abc import ABC, abstractmethod
from typing import Any, Dict
import os
import subprocess

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

    def _generate_requirements(self):
        """Generate requirements.txt"""
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
