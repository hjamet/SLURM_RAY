from abc import ABC, abstractmethod
from typing import Any, Dict, List
import os
import subprocess
import sys
import importlib.metadata
import site
import json


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
    def run(self, cancel_old_jobs: bool = True, wait: bool = True) -> Any:
        """
        Run the job on the backend.

        Args:
            cancel_old_jobs (bool): Whether to cancel old jobs before running
            wait (bool): Whether to wait for the job to finish. If False, returns job_id immediately.

        Returns:
            Any: The result of the execution if wait=True, else job ID.
        """
        pass

    def get_result(self, job_id: str) -> Any:
        """
        Get result for a specific job ID if available.
        Returns None if not finished.
        """
        return None

    def get_logs(self, job_id: str) -> Any:
        """
        Get logs for a specific job ID.
        Returns generator or string.
        """
        return []

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
            ["pip", "list", "-e", "--format=json"], capture_output=True, text=True
        )

        if result.returncode == 0 and result.stdout.strip():
            import json

            try:
                packages = json.loads(result.stdout)
                for pkg in packages:
                    name = pkg.get("name", "").strip()
                    if name:
                        # Clean extras e.g. package[extra] -> package
                        if "[" in name:
                            name = name.split("[")[0]
                        editable_packages.add(name.lower())
            except json.JSONDecodeError:
                # Fall back to text parsing if JSON fails
                pass

        # Fallback to standard text format if JSON not available or failed
        if not editable_packages:
            result = subprocess.run(
                ["pip", "list", "-e"], capture_output=True, text=True
            )

            if result.returncode == 0:
                # Parse table format: skip header lines, extract package names
                lines = result.stdout.strip().split("\n")
                for line in lines:
                    # Skip header lines
                    if not line.strip() or line.startswith("Package") or "---" in line:
                        continue
                    # Extract package name (first column)
                    parts = line.split()
                    if parts:
                        package_name = parts[0].strip()
                        # Clean extras e.g. package[extra] -> package
                        if "[" in package_name:
                            package_name = package_name.split("[")[0]
                        editable_packages.add(package_name.lower())

        if result.returncode != 0:
            if self.logger:
                self.logger.warning(
                    f"Failed to detect editable packages: {result.stderr}"
                )
            return set()

        if self.logger and editable_packages:
            self.logger.info(
                f"Detected editable packages: {', '.join(sorted(editable_packages))}"
            )

        return editable_packages

    def _get_editable_package_source_paths(self) -> List[str]:
        """
        Get source directory paths for all editable packages.
        Returns paths relative to pwd_path that need to be uploaded.

        Returns:
            List[str]: List of relative paths to source directories
        """
        editable_packages = self._get_editable_packages()
        source_paths = []

        # Find site-packages directory
        site_packages = None
        for path in sys.path:
            if path.endswith("site-packages"):
                site_packages = path
                break

        if not site_packages and self.logger:
            self.logger.warning("Could not find site-packages directory in sys.path")

        for pkg_name in editable_packages:
            location = None

            # Method 0: Modern PEP 660 / importlib.metadata detection (Preferred)
            try:
                # Use standard library to find distribution
                dist = importlib.metadata.distribution(pkg_name)
                
                # Check for direct_url.json (PEP 610) using read_text (safer than locate_file)
                content = dist.read_text("direct_url.json")
                if content:
                    data = json.loads(content)
                    # Check if it's a file URL (local)
                    if data.get("url", "").startswith("file://"):
                        # Extract path from URL
                        candidate_path = data["url"][7:]  # Remove file://
                        if os.path.exists(candidate_path):
                            location = candidate_path
                            if self.logger:
                                self.logger.debug(f"Detected editable package {pkg_name} via direct_url.json provided: {location}")
            except Exception as e:
                # Fallback to other methods if this fails
                if self.logger:
                    self.logger.debug(f"Modern detection failed for {pkg_name}: {e}")

            # Method 1: Try .egg-link file (common for older pip editable installs)
            # Also handle name normalization (trail-rag -> trail_rag)
            normalized_name = pkg_name.replace("-", "_")

            if not location and site_packages:
                # Check for .egg-link
                egg_link_path = os.path.join(
                    site_packages, f"{normalized_name}.egg-link"
                )
                if not os.path.exists(egg_link_path):
                    # Try with original name
                    egg_link_path = os.path.join(site_packages, f"{pkg_name}.egg-link")

                if os.path.exists(egg_link_path):
                    try:
                        with open(egg_link_path, "r") as f:
                            # .egg-link contains path on first line
                            content = f.readline().strip()
                            if content:
                                location = content
                    except Exception as e:
                        if self.logger:
                            self.logger.debug(f"Error reading {egg_link_path}: {e}")

                # Method 2: Try .pth file (used by some tools including Poetry sometimes)
                if not location:
                    pth_path = os.path.join(site_packages, f"{normalized_name}.pth")
                    if not os.path.exists(pth_path):
                        pth_path = os.path.join(site_packages, f"{pkg_name}.pth")

                    if os.path.exists(pth_path):
                        try:
                            with open(pth_path, "r") as f:
                                # .pth can contain comments or imports, we look for a valid path
                                for line in f:
                                    line = line.strip()
                                    if (
                                        line
                                        and not line.startswith("#")
                                        and not line.startswith("import")
                                    ):
                                        if os.path.exists(line):
                                            location = line
                                            break
                        except Exception as e:
                            if self.logger:
                                self.logger.debug(f"Error reading {pth_path}: {e}")

            # Method 3: Fallback to uv pip show
            if not location:
                try:
                    result = subprocess.run(
                        ["uv", "pip", "show", pkg_name], capture_output=True, text=True
                    )

                    if result.returncode == 0:
                        # Parse Location field from pip show output
                        for line in result.stdout.split("\n"):
                            if line.startswith("Location:"):
                                loc_candidate = line.split(":", 1)[1].strip()
                                # If pip show returns site-packages, it's likely wrong for editable
                                # (unless it's a flat layout installed there, which is rare for editable)
                                if "site-packages" not in loc_candidate:
                                    location = loc_candidate
                                break
                except FileNotFoundError:
                    # uv not installed
                    pass
                except Exception as e:
                    if self.logger:
                        self.logger.debug(f"uv pip show failed: {e}")

            if not location:
                if self.logger:
                    self.logger.warning(
                        f"Could not determine source location for editable package {pkg_name}"
                    )
                continue

            # Convert to absolute path
            location_abs = os.path.abspath(location)
            pwd_abs = os.path.abspath(self.launcher.pwd_path)

            # Check if location is within current project
            # Note: For monorepos or specific setups, an editable package MIGHT be outside pwd.
            # But SlurmRay usually expects everything to be self-contained or uploaded explicitly.
            # However, the user wants to support "uploading what's needed".
            # If the editable package is INSIDE the project, we calculate relative path.
            # If it's OUTSIDE, we might need to handle it (e.g. by copying it), but
            # the current logic seems to enforce it being inside or at least relative-able.
            #
            # UPDATE: For editable packages that ARE strictly the project itself (e.g. '.' installed as editable),
            # the location detected might be the project root itself.
            # In this case location_abs == pwd_abs (or close to it).
            # We should allow this.

            # Special case for "outside project" warning:
            # If thedetected location matches the project path we are good.
            # If it is TRULY outside, we warn.
            
            if not location_abs.startswith(pwd_abs):
                # Only warn if it's REALLY outside.
                pass 
                # But wait, original code skipped it.
                # If we detected it correctly (e.g. /home/lopilo/code/trail-rag) 
                # and pwd is /home/lopilo/code/trail-rag, then it startswith() is True.
                # The issue before was detecting /.../site-packages which was NOT starting with pwd_abs.
                pass

            if not location_abs.startswith(pwd_abs):
                if self.logger:
                    self.logger.warning(
                        f"Editable package {pkg_name} location {location} is outside project {self.launcher.pwd_path}. Skipping auto-upload for now."
                    )
                continue

            # Get relative path from pwd_path
            try:
                rel_location = os.path.relpath(location_abs, pwd_abs)
            except ValueError:
                # Paths are on different drives (Windows) or cannot be made relative
                if self.logger:
                    self.logger.warning(
                        f"Cannot make relative path for {location_abs} from {pwd_abs}"
                    )
                continue

            # Determine what to upload based on layout
            # The location points to the package directory (e.g., src/trail_rag or trail_rag)
            parent_dir = os.path.dirname(rel_location)
            package_dir_name = os.path.basename(rel_location)

            rel_path = None
            if rel_location == ".":
                # If location is project root (common with pip install -e .),
                # we need to find where the actual package code is.
                # Check for src/ layout first
                if os.path.isdir(os.path.join(pwd_abs, "src", pkg_name)):
                     rel_path = os.path.join("src", pkg_name)
                elif os.path.isdir(os.path.join(pwd_abs, "src", normalized_name)):
                     rel_path = os.path.join("src", normalized_name)
                # Check for flat layout
                elif os.path.isdir(os.path.join(pwd_abs, pkg_name)):
                     rel_path = pkg_name
                elif os.path.isdir(os.path.join(pwd_abs, normalized_name)):
                     rel_path = normalized_name
                
                if self.logger and rel_path:
                    self.logger.debug(f"Resolved editable package {pkg_name} from root to {rel_path}")
            
            # Check if it's a src/ layout
            elif os.path.basename(parent_dir) == "src":
                # Layout src/: upload src/ directory
                rel_path = parent_dir  # e.g., "src"
            else:
                # Layout flat: location is directly package_name/
                if parent_dir == "." or parent_dir == "":
                    # Package is at root level, upload the package directory
                    rel_path = package_dir_name  # e.g., "trail_rag"
                else:
                    # Package is in a subdirectory, upload the parent
                    rel_path = parent_dir

            # Validate rel_path before adding
            if (
                rel_path
                and rel_path != "."
                and rel_path != ".."
                and not rel_path.startswith("./")
                and not rel_path.startswith("../")
            ):
                if rel_path not in source_paths:
                    source_paths.append(rel_path)
                    if self.logger:
                        self.logger.info(
                            f"Auto-detected editable package source: {rel_path} (from package {pkg_name})"
                        )

        return source_paths

    def _ensure_pip_chill_installed(self):
        """
        Ensure pip-chill is installed in the current environment.
        Raises RuntimeError if installation fails.
        """
        # Suppress pkg_resources deprecation warning from pip_chill
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning, module="pip_chill")
            warnings.filterwarnings("ignore", message=".*pkg_resources.*", category=UserWarning)
            try:
                import pip_chill
                return
            except ImportError:
                if self.logger:
                    self.logger.info("pip-chill not found, installing...")

                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "pip-chill"],
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                    raise RuntimeError(
                        f"Failed to install pip-chill: {error_msg}\n"
                        f"Command: {sys.executable} -m pip install pip-chill"
                    )

                if self.logger:
                    self.logger.info("pip-chill installed successfully")

    def _run_pip_chill(self):
        """
        Run pip-chill and return its output.
        Tries to use pip-chill directly as Python module first,
        falls back to subprocess if needed.
        Returns stdout on success, raises RuntimeError on failure.
        """
        # Ensure pip-chill is installed
        self._ensure_pip_chill_installed()

        # Suppress pkg_resources deprecation warning from pip_chill
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning, module="pip_chill")
            warnings.filterwarnings("ignore", message=".*pkg_resources.*", category=UserWarning)

            # Try to use pip-chill directly as Python module
            try:
                from pip_chill import chill

                # chill() returns a generator of groups of Distribution objects
                # Each group contains Distribution objects with name and version attributes
                dist_groups = list(chill())
                requirements_lines = []
                for group in dist_groups:
                    for dist in group:
                        requirements_lines.append(f"{dist.name}=={dist.version}")

                if self.logger:
                    self.logger.debug("✅ Using pip-chill directly as Python module")

                return "\n".join(requirements_lines) + "\n"
            except (ImportError, AttributeError, TypeError) as e:
                # If direct import/execution fails, fall back to subprocess
                if self.logger:
                    self.logger.warning(
                        f"⚠️ Direct pip-chill import/execution failed: {e}. Falling back to subprocess."
                    )

                # Use sys.executable to ensure we use the correct Python/venv
                # Also suppress warnings in subprocess by setting PYTHONWARNINGS
                import os
                env = os.environ.copy()
                env["PYTHONWARNINGS"] = "ignore::UserWarning"
                result = subprocess.run(
                    [sys.executable, "-m", "pip_chill"],
                    capture_output=True,
                    text=True,
                    cwd=self.launcher.project_path,
                    env=env,
                )

                if result.returncode != 0:
                    error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                    raise RuntimeError(
                        f"Failed to run pip-chill: {error_msg}\n"
                        f"Command: {sys.executable} -m pip_chill"
                    )

                if self.logger:
                    self.logger.info("🔄 Using subprocess fallback for pip-chill")

                return result.stdout

    @staticmethod
    def _is_package_local(package_name):
        """Check if a package is installed locally (editable or in project) vs site-packages."""
        if not package_name: return False
        try:
            # Get distribution info
            # Note: package name must be exact distribution name
            dist = importlib.metadata.distribution(package_name)
            
            # Check for direct_url.json (PEP 610) - best for editable installs
            try:
                direct_url_path = dist.locate_file("direct_url.json")
                if os.path.exists(direct_url_path):
                    with open(direct_url_path, "r") as f:
                        data = json.load(f)
                        if data.get("url", "").startswith("file://"):
                            # It's a local file URL, likely editable or local install
                            return True
            except Exception:
                pass
            
            # Get site-packages directories for comparison
            site_packages_dirs = site.getsitepackages()
            if hasattr(site, "getusersitepackages"):
                user_site = site.getusersitepackages()
                if user_site:
                    site_packages_dirs = list(site_packages_dirs) + [user_site]
            
            # Normalize site-packages paths
            site_packages_dirs = [os.path.abspath(p) for p in site_packages_dirs]

            # Fallback: check file locations
            files = dist.files
            if not files:
                return False
                
            # Iterate over files to find where the source is located
            # Editable installs will have source files outside site-packages
            # while dist-info might be inside site-packages.
            for file_path in files:
                try:
                    # locate_file returns absolute path usually, but ensure it
                    abs_path = os.path.abspath(str(dist.locate_file(file_path)))
                    
                    # Optimization: Skip files that are clearly within the dist-info directory used for metadata
                    # (which we know is likely in site-packages if we are here)
                    if ".dist-info" in abs_path or ".egg-info" in abs_path:
                        continue
                        
                    # Check if this file is in any site-packages directory
                    is_in_site = False
                    for site_dir in site_packages_dirs:
                        if abs_path.startswith(site_dir):
                            is_in_site = True
                            break
                    
                    # If we found a file (likely source code) OUTSIDE site-packages, it's local/editable
                    if not is_in_site:
                        return True
                        
                except Exception:
                    continue
            
            # If we iterated all interesting files and they were all in site-packages, it's NOT local
            return False
            
        except Exception:
            return False

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
            if not line or line.startswith("#"):
                return None
            # Split by ==, @, or other operators to get package name
            name_part = (
                line.split("==")[0]
                .split(" @ ")[0]
                .split("<")[0]
                .split(">")[0]
                .split(";")[0]
                .strip()
            )
            # Clean extras e.g. package[extra] -> package
            if "[" in name_part:
                name_part = name_part.split("[")[0]
            return name_part.lower()

        # Helper function to check if a package is local (not in site-packages)
        # Refactored to static method for testing
        is_package_local = self._is_package_local

        # Check if we should skip regeneration
        if not force_regenerate and os.path.exists(req_file):
            # Get current environment packages hash
            try:
                pip_chill_output = self._run_pip_chill()
                current_env_lines = pip_chill_output.strip().split("\n")
                
                # Filter local packages from hash computation for consistency
                # We filter packages that are detected as local (editable or not in site-packages)
                filtered_env_lines = []
                for line in current_env_lines:
                    pkg_name = get_package_name(line)
                    if pkg_name and is_package_local(pkg_name):
                        continue
                    filtered_env_lines.append(line)
                current_env_lines = filtered_env_lines

                current_env_hash = dep_manager.compute_requirements_hash(
                    current_env_lines
                )

                # Check stored environment hash
                stored_env_hash = dep_manager.get_stored_env_hash()
                if stored_env_hash == current_env_hash:
                    # Environment hasn't changed, requirements.txt should be up to date
                    if self.logger:
                        self.logger.info(
                            "Environment unchanged, requirements.txt is up to date, skipping regeneration."
                        )
                    return
            except RuntimeError as e:
                # If pip-chill fails, we can't check hash, so regenerate
                if self.logger:
                    self.logger.warning(
                        f"Could not check environment hash: {e}. Regenerating requirements.txt."
                    )

        # Generate requirements.txt
        if self.logger:
            self.logger.info("Generating requirements.txt...")

        # Use pip-chill to generate requirements
        try:
            requirements_content = self._run_pip_chill()
            if self.logger:
                self.logger.info("Generated requirements.txt using pip-chill")
        except RuntimeError as e:
            raise RuntimeError(
                f"Failed to generate requirements.txt: {e}\n"
                f"Please ensure pip-chill can be installed or is available in your environment."
            )

        # Write initial requirements to file
        with open(req_file, "w") as file:
            file.write(requirements_content)

        # Verify file was created
        if not os.path.exists(req_file):
            raise FileNotFoundError(f"requirements.txt was not created at {req_file}")

        import dill

        dill_version = dill.__version__

        with open(req_file, "r") as file:
            lines = file.readlines()

            # Filter out slurmray, ray and dill
            lines = [
                line
                for line in lines
                if "slurmray" not in line and "ray" not in line and "dill" not in line
            ]

            # Get editable packages list (source of truth)
            try:
                editable_packages_set = self._get_editable_packages()
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Failed to get editable packages for filtering: {e}")
                editable_packages_set = set()

            # Filter out local packages (development installs) using robust detection
            filtered_lines = []
            for line in lines:
                pkg_name = get_package_name(line)
                if pkg_name:
                    # Check against pip list -e (handles trail-rag even if static check fails)
                    # Handle dash/underscore normalization: pkg_name is lowercased by get_package_name
                    # editable_packages_set contains lowercased names
                    normalized_name = pkg_name.replace("_", "-")
                    
                    is_editable = (
                        pkg_name in editable_packages_set 
                        or normalized_name in editable_packages_set
                        or pkg_name.replace("-", "_") in editable_packages_set
                    )

                    if is_editable or self._is_package_local(pkg_name):
                        if self.logger:
                            self.logger.info(f"Excluding local package from requirements: {pkg_name}")
                        continue
                filtered_lines.append(line)
            lines = filtered_lines

            # Filter out ray dependencies that pip-chill picks up but should be managed by ray installation
            # This prevents version conflicts when moving between Python versions (e.g. 3.12 local -> 3.8 remote)
            ray_deps = [
                "aiohttp",
                "colorful",
                "opencensus",
                "opentelemetry",
                "py-spy",
                "uvicorn",
                "uvloop",
                "watchfiles",
                "grpcio",
                "tensorboardX",
                "gpustat",
                "prometheus-client",
                "smart-open",
            ]

            # Also filter out nvidia-* packages which are heavy and usually managed by torch or pre-installed drivers
            # This avoids OOM kills during pip install on limited resources servers
            lines = [
                line
                for line in lines
                if not any(dep in line.split("==")[0] for dep in ray_deps)
                and not line.startswith("nvidia-")
            ]

            # Remove versions constraints to allow remote pip to resolve compatible versions for its Python version
            # This is critical when local is Python 3.12+ and remote is older (e.g. 3.8)
            lines = [
                line.split("==")[0].split(" @ ")[0].strip() + "\n" for line in lines
            ]

            # Add pinned dill version to ensure serialization compatibility
            lines.append(f"dill=={dill_version}\n")

            # Add ray[default] without pinning version (to allow best compatible on remote)
            lines.append("ray[default]\n")

            # Ensure torch is present (common dependency)
            if not any("torch" in line for line in lines):
                lines.append("torch\n")

        with open(req_file, "w") as file:
            file.writelines(lines)

            # Store hash of environment for future checks
        try:
            pip_chill_output = self._run_pip_chill()
            env_lines = pip_chill_output.strip().split("\n")
            
            # Filter local packages from hash computation for consistency
            filtered_env_lines = []
            for line in env_lines:
                pkg_name = get_package_name(line)
                if pkg_name and is_package_local(pkg_name):
                    continue
                filtered_env_lines.append(line)
            env_lines = filtered_env_lines
            
            env_hash = dep_manager.compute_requirements_hash(env_lines)
            dep_manager.store_env_hash(env_hash)
        except RuntimeError as e:
            # If pip-chill fails for hash computation, log warning but don't fail
            # The requirements.txt was generated successfully, hash is just for optimization
            if self.logger:
                self.logger.warning(
                    f"Could not compute environment hash: {e}. Requirements.txt was generated successfully."
                )

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

        with open(req_file, "r") as f:
            local_reqs_lines = f.readlines()

        # If venv_command_prefix is empty, it means we are recreating/creating the venv
        # In this case, we should treat it as an empty environment and install everything
        # (ignoring system packages unless --system-site-packages is used, which is not the default)
        if not venv_command_prefix:
            self.logger.info(
                "New virtualenv detected (or force reinstall): installing all requirements."
            )
            to_install = local_reqs_lines
            # Write full list
            delta_file = os.path.join(
                self.launcher.project_path, "requirements_to_install.txt"
            )
            with open(delta_file, "w") as f:
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
                self.logger.info(
                    "Force reinstall enabled: ignoring requirements cache."
                )
            else:
                self.logger.info("Scanning remote packages (no cache found)...")
            cmd = f"{venv_command_prefix} uv pip list --format=freeze"
            try:
                stdin, stdout, stderr = ssh_client.exec_command(cmd)
                exit_status = stdout.channel.recv_exit_status()
                if exit_status == 0:
                    remote_lines = [
                        l + "\n" for l in stdout.read().decode("utf-8").splitlines()
                    ]
                    dep_manager.save_cache(remote_lines)
                else:
                    # If pip list fails (e.g. venv not active or created), we assume empty
                    self.logger.warning(
                        "Remote pip list failed (venv might not exist)."
                    )
            except Exception as e:
                self.logger.warning(f"Failed to scan remote: {e}")

        # Compare
        to_install = dep_manager.compare(local_reqs_lines, remote_lines)

        # Write delta file
        delta_file = os.path.join(
            self.launcher.project_path, "requirements_to_install.txt"
        )
        with open(delta_file, "w") as f:
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
        if hasattr(self.launcher, "local_python_version"):
            local_version_str = self.launcher.local_python_version
            import re

            match = re.match(r"(\d+)\.(\d+)\.(\d+)", local_version_str)
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
                cmd = f"{pyenv_command} --version"
            else:
                # Fallback to system Python
                cmd = "python3 --version"

            stdin, stdout, stderr = ssh_client.exec_command(cmd)
            remote_version_output = stdout.read().decode("utf-8").strip()

            if remote_version_output:
                # Extract version from "Python X.Y.Z"
                import re

                match = re.search(r"(\d+)\.(\d+)\.(\d+)", remote_version_output)
                if match:
                    remote_major = int(match.group(1))
                    remote_minor = int(match.group(2))
                    remote_micro = int(match.group(3))

                    if self.logger:
                        version_source = "pyenv" if pyenv_command else "system"
                        self.logger.info(
                            f"Remote Python version ({version_source}): {remote_version_output}"
                        )

                    # Check compatibility: same major.minor = compatible
                    is_compatible = (
                        local_major == remote_major and local_minor == remote_minor
                    )

                    if is_compatible:
                        if self.logger:
                            self.logger.info(
                                "✅ Python versions are compatible (same major.minor)"
                            )
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
        stdout_output = stdout.read().decode("utf-8").strip()
        stderr_output = stderr.read().decode("utf-8").strip()

        # Check if pyenv is available (either in output or via exit status)
        pyenv_available = False
        if "NOT_FOUND" not in stdout_output and exit_status == 0:
            # Try another method: check if pyenv command exists after init
            test_cmd2 = 'bash -c \'export PATH="$HOME/.pyenv/bin:$PATH" && eval "$(pyenv init -)" 2>/dev/null && command -v pyenv 2>&1 || echo "NOT_FOUND"\''
            stdin2, stdout2, stderr2 = ssh_client.exec_command(test_cmd2)
            exit_status2 = stdout2.channel.recv_exit_status()
            stdout_output2 = stdout2.read().decode("utf-8").strip()

            if "NOT_FOUND" not in stdout_output2 and exit_status2 == 0:
                pyenv_available = True
                if self.logger:
                    self.logger.info(
                        f"✅ pyenv found on remote server (initialized via shell)"
                    )

        # Method 2: Try direct path check (for system-wide or shared installations)
        if not pyenv_available:
            test_cmd3 = 'bash -c \'export PATH="$HOME/.pyenv/bin:/usr/local/bin:/opt/pyenv/bin:$PATH" && command -v pyenv 2>&1 || which pyenv 2>&1 || echo "NOT_FOUND"\''
            stdin3, stdout3, stderr3 = ssh_client.exec_command(test_cmd3)
            exit_status3 = stdout3.channel.recv_exit_status()
            stdout_output3 = stdout3.read().decode("utf-8").strip()

            if (
                "NOT_FOUND" not in stdout_output3
                and exit_status3 == 0
                and stdout_output3
            ):
                # Try to initialize it
                test_cmd4 = f'bash -c \'export PATH="$HOME/.pyenv/bin:/usr/local/bin:/opt/pyenv/bin:$PATH" && eval "$(pyenv init -)" 2>/dev/null && pyenv --version 2>&1 || echo "NOT_FOUND"\''
                stdin4, stdout4, stderr4 = ssh_client.exec_command(test_cmd4)
                exit_status4 = stdout4.channel.recv_exit_status()
                stdout_output4 = stdout4.read().decode("utf-8").strip()

                if "NOT_FOUND" not in stdout_output4 and exit_status4 == 0:
                    pyenv_available = True
                    if self.logger:
                        self.logger.info(
                            f"✅ pyenv found on remote server: {stdout_output3}"
                        )

        if not pyenv_available:
            if self.logger:
                self.logger.warning(
                    "⚠️ pyenv not available on remote server, falling back to system Python"
                )
            return None

        # Build the pyenv initialization command that works
        # Use the same initialization method that worked during detection
        pyenv_init_cmd = 'export PATH="$HOME/.pyenv/bin:/usr/local/bin:/opt/pyenv/bin:$PATH" && eval "$(pyenv init -)" 2>/dev/null'

        # Check if the Python version is already installed
        check_cmd = f'bash -c \'{pyenv_init_cmd} && pyenv versions --bare | grep -E "^{python_version}$" || echo ""\''
        stdin, stdout, stderr = ssh_client.exec_command(check_cmd)
        exit_status = stdout.channel.recv_exit_status()
        installed_versions = stdout.read().decode("utf-8").strip()

        if python_version not in installed_versions.split("\n"):
            # Version not installed, try to install it
            if self.logger:
                self.logger.info(
                    f"📦 Installing Python {python_version} via pyenv (this may take a few minutes)..."
                )

            # Install Python version via pyenv (with timeout to avoid hanging)
            # Note: pyenv install can take a long time, so we use a timeout
            install_cmd = f"bash -c '{pyenv_init_cmd} && timeout 600 pyenv install -s {python_version} 2>&1'"
            stdin, stdout, stderr = ssh_client.exec_command(install_cmd, get_pty=True)

            # Wait for command to complete (with timeout)
            import time

            start_time = time.time()
            timeout_seconds = 600  # 10 minutes timeout

            while stdout.channel.exit_status_ready() == False:
                if time.time() - start_time > timeout_seconds:
                    if self.logger:
                        self.logger.warning(
                            f"⚠️ pyenv install timeout after {timeout_seconds}s, falling back to system Python"
                        )
                    return None
                time.sleep(1)

            exit_status = stdout.channel.recv_exit_status()
            stderr_output = stderr.read().decode("utf-8")

            if exit_status != 0:
                if self.logger:
                    self.logger.warning(
                        f"⚠️ Failed to install Python {python_version} via pyenv: {stderr_output}"
                    )
                    self.logger.warning("⚠️ Falling back to system Python")
                return None

            if self.logger:
                self.logger.info(
                    f"✅ Python {python_version} installed successfully via pyenv"
                )
                print(
                    f"✅ Python {python_version} installed and will be used via pyenv"
                )
        else:
            if self.logger:
                self.logger.info(
                    f"✅ Python {python_version} already installed via pyenv"
                )
                print(f"✅ Python {python_version} will be used via pyenv")

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

    def _update_retention_timestamp(self, ssh_client, project_dir, retention_days):
        """
        Update retention timestamp and days for a project on the cluster.

        Args:
            ssh_client: SSH client connected to the cluster
            project_dir: Path to the project directory on the cluster (relative or absolute)
            retention_days: Number of days to retain files (1-30)
        """
        import time

        timestamp = str(int(time.time()))
        # Ensure project directory exists
        ssh_client.exec_command(f"mkdir -p {project_dir}")
        # Write timestamp file
        stdin, stdout, stderr = ssh_client.exec_command(
            f"echo '{timestamp}' > {project_dir}/.retention_timestamp"
        )
        stdout.channel.recv_exit_status()
        # Write retention days file
        stdin, stdout, stderr = ssh_client.exec_command(
            f"echo '{retention_days}' > {project_dir}/.retention_days"
        )
        stdout.channel.recv_exit_status()
