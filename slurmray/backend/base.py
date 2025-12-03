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

    def _get_editable_packages(self):
        """
        Detect packages installed in editable mode (development installs).
        
        Returns:
            set: Set of package names (normalized to lowercase) installed in editable mode.
                 Returns empty set if detection fails.
        """
        editable_packages = set()
        
        # Try JSON format first (more reliable parsing)
        result = subprocess.run(
            ["pip", "list", "-e", "--format=json"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and result.stdout.strip():
            import json
            try:
                packages = json.loads(result.stdout)
                for pkg in packages:
                    name = pkg.get('name', '').strip()
                    if name:
                        # Clean extras e.g. package[extra] -> package
                        if '[' in name:
                            name = name.split('[')[0]
                        editable_packages.add(name.lower())
            except json.JSONDecodeError:
                # Fall back to text parsing if JSON fails
                pass
        
        # Fallback to standard text format if JSON not available or failed
        if not editable_packages:
            result = subprocess.run(
                ["pip", "list", "-e"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Parse table format: skip header lines, extract package names
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    # Skip header lines
                    if not line.strip() or line.startswith('Package') or '---' in line:
                        continue
                    # Extract package name (first column)
                    parts = line.split()
                    if parts:
                        package_name = parts[0].strip()
                        # Clean extras e.g. package[extra] -> package
                        if '[' in package_name:
                            package_name = package_name.split('[')[0]
                        editable_packages.add(package_name.lower())
        
        if result.returncode != 0:
            if self.logger:
                self.logger.warning(f"Failed to detect editable packages: {result.stderr}")
            return set()
        
        if self.logger and editable_packages:
            self.logger.info(f"Detected editable packages: {', '.join(sorted(editable_packages))}")
        
        return editable_packages

    def _generate_requirements(self, force_regenerate=False):
        """
        Generate requirements.txt.
        
        Args:
            force_regenerate: If True, always regenerate. If False, check if dependencies changed.
        """
        from slurmray.utils import DependencyManager
        
        req_file = os.path.join(self.launcher.project_path, "requirements.txt")
        dep_manager = DependencyManager(self.launcher.project_path, self.logger)
        
        # Helper function to extract package name from a requirement line
        def get_package_name(line):
            """Extract normalized package name from requirement line."""
            line = line.strip()
            if not line or line.startswith('#'):
                return None
            # Split by ==, @, or other operators to get package name
            name_part = line.split("==")[0].split(" @ ")[0].split("<")[0].split(">")[0].split(";")[0].strip()
            # Clean extras e.g. package[extra] -> package
            if '[' in name_part:
                name_part = name_part.split('[')[0]
            return name_part.lower()
        
        # Detect editable packages once (used for filtering and hash computation)
        editable_packages = self._get_editable_packages()
        
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
                # Filter editable packages from hash computation for consistency
                if editable_packages:
                    current_env_lines = [
                        line for line in current_env_lines
                        if get_package_name(line) not in editable_packages
                    ]
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
            
            # Filter out editable packages (development installs)
            if editable_packages:
                lines = [
                    line for line in lines
                    if get_package_name(line) not in editable_packages
                ]
            
            # Filter out ray dependencies that pip-chill picks up but should be managed by ray installation
            # This prevents version conflicts when moving between Python versions (e.g. 3.12 local -> 3.8 remote)
            ray_deps = ["aiohttp", "colorful", "opencensus", "opentelemetry", "py-spy", "uvicorn", "uvloop", "watchfiles", "grpcio", "tensorboardX", "gpustat", "prometheus-client", "smart-open"]
            
            # Also filter out nvidia-* packages which are heavy and usually managed by torch or pre-installed drivers
            # This avoids OOM kills during pip install on limited resources servers
            lines = [
                line for line in lines 
                if not any(dep in line.split("==")[0] for dep in ray_deps) 
                and not line.startswith("nvidia-")
            ]
            
            # Remove versions constraints to allow remote pip to resolve compatible versions for its Python version
            # This is critical when local is Python 3.12+ and remote is older (e.g. 3.8)
            lines = [line.split("==")[0].split(" @ ")[0].strip() + "\n" for line in lines]
            
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
            # Filter editable packages from hash computation for consistency
            if editable_packages:
                env_lines = [
                    line for line in env_lines
                    if get_package_name(line) not in editable_packages
                ]
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

        # If venv_command_prefix is empty, it means we are recreating/creating the venv
        # In this case, we should treat it as an empty environment and install everything
        # (ignoring system packages unless --system-site-packages is used, which is not the default)
        if not venv_command_prefix:
            self.logger.info("New virtualenv detected (or force reinstall): installing all requirements.")
            to_install = local_reqs_lines
            # Write full list
            delta_file = os.path.join(self.launcher.project_path, "requirements_to_install.txt")
            with open(delta_file, 'w') as f:
                f.writelines(to_install)
            return delta_file
            
        cache_lines = dep_manager.load_cache()
        remote_lines = []
        
        # Only skip remote check if cache is non-empty AND not force reinstall
        if cache_lines and not self.launcher.force_reinstall_venv:
            self.logger.info("Using cached requirements list.")
            remote_lines = cache_lines
        else:
            if self.launcher.force_reinstall_venv:
                 self.logger.info("Force reinstall enabled: ignoring requirements cache.")
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
