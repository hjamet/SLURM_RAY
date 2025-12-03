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

    def _check_python_version_compatibility(self, ssh_client=None, pyenv_command=None):
        """
        Check Python version compatibility between local and remote environments.
        Uses pyenv if available, otherwise falls back to system Python.
        
        Args:
            ssh_client: Optional SSH client for remote version check. If None, only logs local version.
            pyenv_command: Optional pyenv command prefix (from _get_pyenv_python_command)
            
        Returns:
            bool: True if versions are compatible (same major.minor), False otherwise
        """
        # Get local version from launcher if available, otherwise use sys.version_info
        if hasattr(self.launcher, 'local_python_version'):
            local_version_str = self.launcher.local_python_version
            import re
            match = re.match(r'(\d+)\.(\d+)\.(\d+)', local_version_str)
            if match:
                local_major = int(match.group(1))
                local_minor = int(match.group(2))
                local_micro = int(match.group(3))
            else:
                local_version = sys.version_info
                local_major = local_version.major
                local_minor = local_version.minor
                local_micro = local_version.micro
                local_version_str = f"{local_major}.{local_minor}.{local_micro}"
        else:
            local_version = sys.version_info
            local_major = local_version.major
            local_minor = local_version.minor
            local_micro = local_version.micro
            local_version_str = f"{local_major}.{local_minor}.{local_micro}"
        
        if self.logger:
            self.logger.info(f"Local Python version: {local_version_str}")
        
        if not ssh_client:
            return True  # Assume compatible if we can't check
        
        # Check remote Python version (prefer pyenv if available)
        try:
            if pyenv_command:
                # Use pyenv to get Python version
                cmd = f'{pyenv_command} --version'
            else:
                # Fallback to system Python
                cmd = "python3 --version"
            
            stdin, stdout, stderr = ssh_client.exec_command(cmd)
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
                        version_source = "pyenv" if pyenv_command else "system"
                        self.logger.info(f"Remote Python version ({version_source}): {remote_version_output}")
                    
                    # Check compatibility: same major.minor = compatible
                    is_compatible = (local_major == remote_major and local_minor == remote_minor)
                    
                    if is_compatible:
                        if self.logger:
                            self.logger.info("✅ Python versions are compatible (same major.minor)")
                    else:
                        if local_major != remote_major:
                            if self.logger:
                                self.logger.warning(
                                    f"⚠️ Python major version mismatch: local={local_major}, remote={remote_major}. "
                                    f"This may cause compatibility issues."
                                )
                        else:
                            if self.logger:
                                self.logger.warning(
                                    f"⚠️ Python minor version difference: local={local_major}.{local_minor}, "
                                    f"remote={remote_major}.{remote_minor}. This may cause compatibility issues."
                                )
                    
                    return is_compatible
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Could not check remote Python version: {e}")
        
        # If we can't determine, assume incompatible to be safe
        return False

    def _setup_pyenv_python(self, ssh_client, python_version: str) -> str:
        """
        Setup pyenv on remote server to use the specified Python version.
        
        Args:
            ssh_client: SSH client connected to remote server
            python_version: Python version string (e.g., "3.12.1")
            
        Returns:
            str: Command to use Python via pyenv, or None if pyenv is not available
        """
        if not ssh_client:
            return None
        
        # Try multiple methods to detect and initialize pyenv
        # Method 1: Try to initialize pyenv and check if it works
        # This handles cases where pyenv is installed but needs shell initialization
        test_cmd = 'bash -c \'export PATH="$HOME/.pyenv/bin:$PATH" && eval "$(pyenv init -)" 2>/dev/null && pyenv --version 2>&1 || echo "NOT_FOUND"\''
        stdin, stdout, stderr = ssh_client.exec_command(test_cmd)
        exit_status = stdout.channel.recv_exit_status()
        stdout_output = stdout.read().decode('utf-8').strip()
        stderr_output = stderr.read().decode('utf-8').strip()
        
        # Check if pyenv is available (either in output or via exit status)
        pyenv_available = False
        if "NOT_FOUND" not in stdout_output and exit_status == 0:
            # Try another method: check if pyenv command exists after init
            test_cmd2 = 'bash -c \'export PATH="$HOME/.pyenv/bin:$PATH" && eval "$(pyenv init -)" 2>/dev/null && command -v pyenv 2>&1 || echo "NOT_FOUND"\''
            stdin2, stdout2, stderr2 = ssh_client.exec_command(test_cmd2)
            exit_status2 = stdout2.channel.recv_exit_status()
            stdout_output2 = stdout2.read().decode('utf-8').strip()
            
            if "NOT_FOUND" not in stdout_output2 and exit_status2 == 0:
                pyenv_available = True
                if self.logger:
                    self.logger.info(f"✅ pyenv found on remote server (initialized via shell)")
        
        # Method 2: Try direct path check (for system-wide or shared installations)
        if not pyenv_available:
            test_cmd3 = 'bash -c \'export PATH="$HOME/.pyenv/bin:/usr/local/bin:/opt/pyenv/bin:$PATH" && command -v pyenv 2>&1 || which pyenv 2>&1 || echo "NOT_FOUND"\''
            stdin3, stdout3, stderr3 = ssh_client.exec_command(test_cmd3)
            exit_status3 = stdout3.channel.recv_exit_status()
            stdout_output3 = stdout3.read().decode('utf-8').strip()
            
            if "NOT_FOUND" not in stdout_output3 and exit_status3 == 0 and stdout_output3:
                # Try to initialize it
                test_cmd4 = f'bash -c \'export PATH="$HOME/.pyenv/bin:/usr/local/bin:/opt/pyenv/bin:$PATH" && eval "$(pyenv init -)" 2>/dev/null && pyenv --version 2>&1 || echo "NOT_FOUND"\''
                stdin4, stdout4, stderr4 = ssh_client.exec_command(test_cmd4)
                exit_status4 = stdout4.channel.recv_exit_status()
                stdout_output4 = stdout4.read().decode('utf-8').strip()
                
                if "NOT_FOUND" not in stdout_output4 and exit_status4 == 0:
                    pyenv_available = True
                    if self.logger:
                        self.logger.info(f"✅ pyenv found on remote server: {stdout_output3}")
        
        if not pyenv_available:
            if self.logger:
                self.logger.warning("⚠️ pyenv not available on remote server, falling back to system Python")
            return None
        
        # Build the pyenv initialization command that works
        # Use the same initialization method that worked during detection
        pyenv_init_cmd = 'export PATH="$HOME/.pyenv/bin:/usr/local/bin:/opt/pyenv/bin:$PATH" && eval "$(pyenv init -)" 2>/dev/null'
        
        # Check if the Python version is already installed
        check_cmd = f'bash -c \'{pyenv_init_cmd} && pyenv versions --bare | grep -E "^{python_version}$" || echo ""\''
        stdin, stdout, stderr = ssh_client.exec_command(check_cmd)
        exit_status = stdout.channel.recv_exit_status()
        installed_versions = stdout.read().decode('utf-8').strip()
        
        if python_version not in installed_versions.split('\n'):
            # Version not installed, try to install it
            if self.logger:
                self.logger.info(f"📦 Installing Python {python_version} via pyenv (this may take a few minutes)...")
            
            # Install Python version via pyenv (with timeout to avoid hanging)
            # Note: pyenv install can take a long time, so we use a timeout
            install_cmd = f'bash -c \'{pyenv_init_cmd} && timeout 600 pyenv install -s {python_version} 2>&1\''
            stdin, stdout, stderr = ssh_client.exec_command(install_cmd, get_pty=True)
            
            # Wait for command to complete (with timeout)
            import time
            start_time = time.time()
            timeout_seconds = 600  # 10 minutes timeout
            
            while stdout.channel.exit_status_ready() == False:
                if time.time() - start_time > timeout_seconds:
                    if self.logger:
                        self.logger.warning(f"⚠️ pyenv install timeout after {timeout_seconds}s, falling back to system Python")
                    return None
                time.sleep(1)
            
            exit_status = stdout.channel.recv_exit_status()
            stderr_output = stderr.read().decode('utf-8')
            
            if exit_status != 0:
                if self.logger:
                    self.logger.warning(f"⚠️ Failed to install Python {python_version} via pyenv: {stderr_output}")
                    self.logger.warning("⚠️ Falling back to system Python")
                return None
            
            if self.logger:
                self.logger.info(f"✅ Python {python_version} installed successfully via pyenv")
        else:
            if self.logger:
                self.logger.info(f"✅ Python {python_version} already installed via pyenv")
        
        # Return command to use pyenv Python
        return self._get_pyenv_python_command(python_version)
    
    def _get_pyenv_python_command(self, python_version: str) -> str:
        """
        Get the command to use Python via pyenv.
        
        Args:
            python_version: Python version string (e.g., "3.12.1")
            
        Returns:
            str: Command prefix to use Python via pyenv
        """
        # Return a command that initializes pyenv and sets the version
        # Use the same initialization method that works during detection
        # This will be used in shell scripts
        return f'export PATH="$HOME/.pyenv/bin:/usr/local/bin:/opt/pyenv/bin:$PATH" && eval "$(pyenv init -)" 2>/dev/null && pyenv shell {python_version} && python'
