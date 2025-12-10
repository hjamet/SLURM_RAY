from typing import Any, Callable, List
import sys
import os
import dill
import logging
import signal
import dis
import builtins
import inspect
from typing import Any, Callable, List, Tuple, Set, Generator
from getpass import getpass
import time


from dotenv import load_dotenv

from slurmray.backend.slurm import SlurmBackend
from slurmray.backend.local import LocalBackend
from slurmray.backend.desi import DesiBackend

dill.settings["recurse"] = True


class RayLauncher:
    """A class that automatically connects RAY workers and executes the function requested by the user.

    Official tool from DESI @ HEC UNIL.

    Supports multiple execution modes:
    - **Curnagl mode** (`cluster='curnagl'`): For Slurm-based clusters like Curnagl. Uses sbatch/squeue for job management.
    - **Desi mode** (`cluster='desi'`): For standalone servers like ISIPOL09. Uses Smart Lock scheduling for resource management.
    - **Local mode** (`cluster='local'`): For local execution without remote server/cluster.
    - **Custom IP** (`cluster='<ip_or_hostname>'`): For custom Slurm clusters. Uses the provided IP/hostname.

    The launcher automatically selects the appropriate backend based on the `cluster` parameter and environment detection.
    """

    class FunctionReturn:
        """Object returned when running in asynchronous mode.
        Allows monitoring logs and retrieving the result later.
        """
        def __init__(self, launcher, job_id=None):
            self.launcher = launcher
            self.job_id = job_id
            self._cached_result = None

        @property
        def result(self):
            """Get the result of the function execution.
            Returns "Compute still in progress" if not finished.
            """
            if self._cached_result is not None:
                return self._cached_result

            # Attempt to fetch result from backend
            # We use a new method on backend to check/fetch result without blocking
            if hasattr(self.launcher.backend, "get_result"):
                res = self.launcher.backend.get_result(self.job_id)
                if res is not None:
                    self._cached_result = res
                    return res
            
            return "Compute still in progress"

        @property
        def logs(self) -> Generator[str, None, None]:
            """Get the logs of the function execution as a stream (generator)."""
            if hasattr(self.launcher.backend, "get_logs"):
                yield from self.launcher.backend.get_logs(self.job_id)
            else:
                yield "Logs not available for this backend."

        def cancel(self):
            """Cancel the running job."""
            if hasattr(self.launcher.backend, "cancel"):
                self.launcher.backend.cancel(self.job_id)

        def __getstate__(self):
            """Custom serialization to ensure picklability"""
            state = self.__dict__.copy()
            # Ensure launcher is picklable. The launcher itself might have non-picklable attributes (like ssh_client).
            # We rely on RayLauncher and Backend handling their own serialization safety.
            return state

        def __setstate__(self, state):
            self.__dict__.update(state)


    def __init__(
        self,
        project_name: str = None,
        files: List[str] = [],
        modules: List[str] = [],
        node_nbr: int = 1,
        use_gpu: bool = False,
        memory: int = 64,
        max_running_time: int = 60,
        runtime_env: dict = {"env_vars": {}},
        server_run: bool = True,
        server_ssh: str = None,  # Auto-detected from cluster parameter
        server_username: str = None,
        server_password: str = None,
        log_file: str = "logs/RayLauncher.log",
        cluster: str = "curnagl",  # 'curnagl', 'desi', 'local', or custom IP/hostname
        force_reinstall_venv: bool = False,
        retention_days: int = 7,
        asynchronous: bool = False,
    ):
        """Initialize the launcher

        Args:
            project_name (str, optional): Name of the project. Defaults to None.
            files (List[str], optional): List of files to push to the cluster/server. This path must be **relative** to the project directory. Defaults to [].
            modules (List[str], optional): List of modules to load (Slurm mode only). Use `module spider` to see available modules. Ignored in Desi mode. Defaults to None.
            node_nbr (int, optional): Number of nodes to use. For Desi mode, this is always 1 (single server). Defaults to 1.
            use_gpu (bool, optional): Use GPU or not. Defaults to False.
            memory (int, optional): Amount of RAM to use per node in GigaBytes. For Desi mode, this is not enforced (shared resource). Defaults to 64.
            max_running_time (int, optional): Maximum running time of the job in minutes. For Desi mode, this is not enforced by a scheduler. Defaults to 60.
            runtime_env (dict, optional): Environment variables to share between all the workers. Can be useful for issues like https://github.com/ray-project/ray/issues/418. Default to empty.
            server_run (bool, optional): If you run the launcher from your local machine, you can use this parameter to execute your function using online cluster/server ressources. Defaults to True.
            server_ssh (str, optional): If `server_run` is set to true, the address of the server to use. Auto-detected from `cluster` parameter if not provided. Defaults to None (auto-detected).
            server_username (str, optional): If `server_run` is set to true, the username with which you wish to connect. Credentials are automatically loaded from a `.env` file (CURNAGL_USERNAME for Curnagl/custom IP, DESI_USERNAME for Desi) if available. Priority: environment variables → explicit parameter → default ("hjamet" for Curnagl/custom IP, "henri" for Desi).
            server_password (str, optional): If `server_run` is set to true, the password of the user to connect to the server. Credentials are automatically loaded from a `.env` file (CURNAGL_PASSWORD for Curnagl/custom IP, DESI_PASSWORD for Desi) if available. Priority: explicit parameter → environment variables → interactive prompt. CAUTION: never write your password in the code. Defaults to None.
            log_file (str, optional): Path to the log file. Defaults to "logs/RayLauncher.log".
            cluster (str, optional): Cluster/server to use: 'curnagl' (default, Slurm cluster), 'desi' (ISIPOL09/Desi server), 'local' (local execution), or a custom IP/hostname (for custom Slurm clusters). Defaults to "curnagl".
            force_reinstall_venv (bool, optional): Force complete removal and recreation of virtual environment on remote server/cluster. This will delete the existing venv and reinstall all packages from requirements.txt. Use this if the venv is corrupted or you need a clean installation. Defaults to False.
            retention_days (int, optional): Number of days to retain files and venv on the cluster before automatic cleanup. Must be between 1 and 30 days. Defaults to 7.
            asynchronous (bool, optional): If True, the call to the function returns immediately with a FunctionReturn object. Defaults to False.
        """
        # Load environment variables from .env file
        load_dotenv()

        # Normalize cluster parameter
        cluster_lower = cluster.lower()

        # Detect if cluster is a custom IP/hostname (not a known name)
        is_custom_ip = cluster_lower not in ["curnagl", "desi", "local"]

        # Determine cluster type and backend type
        if cluster_lower == "local":
            self.cluster_type = "local"
            self.backend_type = "local"
            # Force local execution
            self._force_local = True
        else:
            self._force_local = False
            if cluster_lower == "desi":
                self.cluster_type = "desi"
                self.backend_type = "desi"
            elif cluster_lower == "curnagl" or is_custom_ip:
                self.cluster_type = "curnagl"  # Use "curnagl" for credential loading
                self.backend_type = "slurm"  # Use SlurmBackend
            else:
                raise ValueError(
                    f"Invalid cluster value: '{cluster}'. Use 'curnagl', 'desi', 'local', or a custom IP/hostname."
                )

        # Determine environment variable names based on cluster type
        if self.cluster_type == "desi":
            env_username_key = "DESI_USERNAME"
            env_password_key = "DESI_PASSWORD"
            default_username = "henri"
        else:  # curnagl or custom IP (both use CURNAGL credentials)
            env_username_key = "CURNAGL_USERNAME"
            env_password_key = "CURNAGL_PASSWORD"
            default_username = "hjamet"

        # Load credentials with priority: .env → explicit parameter → default/prompt
        # Priority 1: Load from environment variables (from .env or system env)
        env_username = os.getenv(env_username_key)
        env_password = os.getenv(env_password_key)

        # For username: explicit parameter → env → default
        if server_username is not None:
            # Explicit parameter provided
            self.server_username = server_username
        elif env_username:
            # Load from environment
            self.server_username = env_username
        else:
            # Use default
            self.server_username = default_username

        # For password: explicit parameter → env → None (will prompt later if needed)
        # Explicit parameter takes precedence over env
        if server_password is not None:
            # Explicit parameter provided
            self.server_password = server_password
        elif env_password:
            # Load from environment
            self.server_password = env_password
        else:
            # None: will be prompted by backend if needed
            self.server_password = None

        # Save the other parameters
        self.project_name = project_name
        self.files = files
        self.modules = modules
        self.node_nbr = node_nbr
        self.use_gpu = use_gpu
        self.memory = memory
        self.max_running_time = max_running_time

        # Validate and save retention_days
        if retention_days < 1 or retention_days > 30:
            raise ValueError(
                f"retention_days must be between 1 and 30, got {retention_days}"
            )
        self.retention_days = retention_days

        # Set default runtime_env and add Ray warning suppression
        if runtime_env is None:
            runtime_env = {"env_vars": {}}
        elif "env_vars" not in runtime_env:
            runtime_env["env_vars"] = {}

        # Suppress Ray FutureWarning about accelerator visible devices
        if "RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO" not in runtime_env["env_vars"]:
            runtime_env["env_vars"]["RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO"] = "0"

        self.runtime_env = runtime_env
        # Update server_run if cluster is "local"
        if hasattr(self, "_force_local") and self._force_local:
            self.server_run = False
        else:
            self.server_run = server_run

        # Auto-detect server_ssh from cluster parameter if not provided
        if self.server_run and server_ssh is None:
            if cluster_lower == "desi":
                self.server_ssh = "130.223.73.209"
            elif cluster_lower == "curnagl":
                self.server_ssh = "curnagl.dcsr.unil.ch"
            elif is_custom_ip:
                # Use the provided IP/hostname directly
                self.server_ssh = cluster
            else:
                # Fallback (should not happen)
                self.server_ssh = "curnagl.dcsr.unil.ch"
        else:
            self.server_ssh = server_ssh or "curnagl.dcsr.unil.ch"

        self.log_file = log_file
        self.force_reinstall_venv = force_reinstall_venv
        self.asynchronous = asynchronous

        # Track which parameters were explicitly passed (for warnings)
        import inspect

        frame = inspect.currentframe()
        args, _, _, values = inspect.getargvalues(frame)
        self._explicit_params = {
            arg: values[arg] for arg in args[1:] if arg in values
        }  # Skip 'self'

        self.__setup_logger()

        # Create the project directory if not exists (needed for pwd_path)
        self.pwd_path = os.getcwd()
        self.module_path = os.path.dirname(os.path.abspath(__file__))
        self.project_path = os.path.join(self.pwd_path, ".slogs", self.project_name)
        if not os.path.exists(self.project_path):
            os.makedirs(self.project_path)

        # Detect local Python version
        self.local_python_version = self._detect_local_python_version()

        # Default modules with specific versions for Curnagl compatibility
        # Using latest stable versions available on Curnagl (SLURM 24.05.3)
        # gcc/13.2.0: Latest GCC version
        # python/3.12.1: Latest Python version on Curnagl
        # cuda/12.6.2: Latest CUDA version
        # cudnn/9.2.0.82-12: Compatible with cuda/12.6.2
        default_modules = ["gcc/13.2.0", "python/3.12.1"]

        # Filter out any gcc or python modules from user list (we use defaults)
        # Allow user to override by providing specific versions
        user_modules = []
        for mod in modules:
            # Skip if it's a gcc or python module (user can override by providing full version)
            if mod.startswith("gcc") or mod.startswith("python"):
                continue
            user_modules.append(mod)

        self.modules = default_modules + user_modules

        if self.use_gpu is True:
            # Check if user provided specific cuda/cudnn versions
            has_cuda = any("cuda" in mod for mod in self.modules)
            has_cudnn = any("cudnn" in mod for mod in self.modules)
            if not has_cuda:
                self.modules.append("cuda/12.6.2")
            if not has_cudnn:
                self.modules.append("cudnn/9.2.0.82-12")

        # --- Validation des Arguments ---
        self._validate_arguments()

        # Check if this code is running on a cluster (only relevant for Slurm, usually)
        self.cluster = os.path.exists("/usr/bin/sbatch")

        # Initialize Backend
        if self.backend_type == "local":
            self.backend = LocalBackend(self)
        elif self.server_run:
            if self.backend_type == "desi":
                self.backend = DesiBackend(self)
            elif self.backend_type == "slurm":
                self.backend = SlurmBackend(self)
            else:
                raise ValueError(
                    f"Unknown backend type: {self.backend_type}. This should not happen."
                )
        elif self.cluster:  # Running ON a cluster (Slurm)
            self.backend = SlurmBackend(self)
        else:
            self.backend = LocalBackend(self)

        # Auto-detect and add editable package source paths to files list
        # Note: Intelligent dependency detection is now done in __call__
        # when we have the function to analyze. We don't auto-add editable packages
        # blindly anymore to avoid adding unwanted files or breaking with complex setups.

    def __setup_logger(self):
        """Setup the logger"""
        # Create the log directory if not exists
        log_dir = os.path.dirname(self.log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # Configure the logger
        self.logger = logging.getLogger(f"RayLauncher-{self.project_name}")
        self.logger.setLevel(logging.INFO)

        # Remove existing handlers to avoid duplication if instantiated multiple times
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        # File handler (constantly rewritten)
        file_handler = logging.FileHandler(self.log_file, mode="w")
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

        # Console handler (only warnings and errors)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_formatter = logging.Formatter("%(levelname)s: %(message)s")
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

    def _detect_local_python_version(self) -> str:
        """Detect local Python version from .python-version file or sys.version_info

        Returns:
            str: Python version in format "X.Y.Z" (e.g., "3.12.1")
        """
        # Try to read from .python-version file first
        python_version_file = os.path.join(self.pwd_path, ".python-version")
        if os.path.exists(python_version_file):
            with open(python_version_file, "r") as f:
                version_str = f.read().strip()
                # Validate format (should be X.Y or X.Y.Z)
                import re

                if re.match(r"^\d+\.\d+(\.\d+)?$", version_str):
                    # If only X.Y, add .0 for micro version
                    if version_str.count(".") == 1:
                        version_str = f"{version_str}.0"
                    self.logger.info(
                        f"Detected Python version from .python-version: {version_str}"
                    )
                    return version_str

        # Fallback to sys.version_info
        version_str = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        self.logger.info(
            f"Detected Python version from sys.version_info: {version_str}"
        )
        return version_str

    def _validate_arguments(self):
        """Validate arguments and warn about inconsistencies"""
        # Validate project_name is not None (required for project-based organization on cluster)
        if self.project_name is None:
            raise ValueError(
                "project_name cannot be None. A project name is required for cluster execution."
            )

        if self.cluster_type == "desi":
            # server_ssh is already set correctly in __init__
            pass

            if self.node_nbr > 1:
                self.logger.warning(
                    f"Warning: Desi cluster only supports single node execution. node_nbr={self.node_nbr} will be ignored (effectively 1)."
                )

            # Only warn if modules were explicitly passed by user (not just defaults)
            # Check if user provided modules beyond the default ones (gcc/python) or GPU modules (cuda/cudnn)
            # GPU modules are added automatically if use_gpu=True, so they don't count as user-provided
            user_provided_modules = [
                m
                for m in self.modules
                if not (
                    m.startswith("gcc")
                    or m.startswith("python")
                    or m.startswith("cuda")
                    or m.startswith("cudnn")
                )
            ]
            if "modules" in self._explicit_params and user_provided_modules:
                self.logger.warning(
                    "Warning: Modules loading is not supported on Desi (no module system). Modules list will be ignored."
                )

            if "memory" in self._explicit_params and self.memory != 64:  # 64 is default
                self.logger.warning(
                    "Warning: Memory allocation is not enforced on Desi (shared resource)."
                )

    def _handle_signal(self, signum, frame):
        """Handle interruption signals (SIGINT, SIGTERM) to cleanup resources"""
        sig_name = signal.Signals(signum).name
        self.logger.warning(f"Signal {sig_name} received. Cleaning up resources...")
        print(f"\nInterruption received ({sig_name}). Canceling job and cleaning up...")
        
        self.cancel()
        sys.exit(1)

    def cancel(self, target: Any = None):
        """
        Cancel a running job.
        
        Args:
            target (Any, optional): The job to cancel. Can be:
                - None: Cancels the last job run by this launcher instance.
                - str: A specific job ID.
                - FunctionReturn: A specific FunctionReturn object.
        """
        if hasattr(self, "backend"):
            job_id = None
            
            # Determine job_id based on target
            if target is None:
                # Fallback to last job
                if hasattr(self.backend, "job_id") and self.backend.job_id:
                    job_id = self.backend.job_id
                elif hasattr(self, "job_id") and self.job_id:
                    job_id = self.job_id
            elif isinstance(target, str):
                job_id = target
            elif isinstance(target, self.FunctionReturn):
                job_id = target.job_id
            
            if job_id:
                self.backend.cancel(job_id)
            else:
                self.logger.warning("No job ID found to cancel.")
        else:
            self.logger.warning("No backend initialized, cannot cancel.")

    def __call__(
        self,
        func: Callable,
        args: dict = None,
        cancel_old_jobs: bool = True,
        serialize: bool = True,
    ) -> Any:
        """Launch the job and return the result

        Args:
            func (Callable): Function to execute. This function should not be remote but can use ray ressources.
            args (dict, optional): Arguments of the function. Defaults to None (empty dict).
            cancel_old_jobs (bool, optional): Cancel the old jobs. Defaults to True.
            serialize (bool, optional): Serialize the function and the arguments. This should be set to False if the function is automatically called by the server. Defaults to True.

        Returns:
            Any: Result of the function
        """
        if args is None:
            args = {}

        # Intelligent dependency detection from function source file
        if self.server_run:
            try:
                from slurmray.scanner import ProjectScanner

                scanner = ProjectScanner(self.pwd_path, self.logger)
                detected_dependencies = scanner.detect_dependencies_from_function(func)

                added_count = 0
                for dep in detected_dependencies:
                    # Skip invalid paths (empty, current directory, etc.)
                    if (
                        not dep
                        or dep == "."
                        or dep == ".."
                        or dep.startswith("./")
                        or dep.startswith("../")
                    ):
                        continue

                    # Skip paths that are outside project or in ignored directories
                    dep_abs = os.path.abspath(os.path.join(self.pwd_path, dep))
                    if not dep_abs.startswith(os.path.abspath(self.pwd_path)):
                        continue

                    # Check if it's a valid file or directory
                    if not os.path.exists(dep_abs):
                        continue

                    # Check if dependency is already covered by existing files/dirs
                    # E.g. if 'src' is in files, 'src/module.py' is covered
                    is_covered = False
                    for existing in self.files:
                        if dep == existing or (dep.startswith(existing + os.sep)):
                            is_covered = True
                            break

                    if not is_covered:
                        self.files.append(dep)
                        added_count += 1

                if added_count > 0:
                    self.logger.info(
                        f"Auto-added {added_count} local dependencies to upload list (from function imports)."
                    )

                # Display warnings for dynamic imports
                if scanner.dynamic_imports_warnings:
                    print("\n" + "=" * 60)
                    print("⚠️  WARNING: Dynamic imports or file operations detected ⚠️")
                    print("=" * 60)
                    print(
                        "The following lines might require files that cannot be auto-detected."
                    )
                    print(
                        "Please verify if you need to add them manually to 'files=[...]':"
                    )
                    for warning in scanner.dynamic_imports_warnings:
                        print(f"  - {warning}")
                    print("=" * 60 + "\n")

                    # Also log them
                    for warning in scanner.dynamic_imports_warnings:
                        self.logger.warning(f"Dynamic import warning: {warning}")

            except Exception as e:
                self.logger.warning(f"Dependency detection from function failed: {e}")

        # Register signal handlers
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        try:
            # Serialize function and arguments
            if serialize:
                self.__serialize_func_and_args(func, args)

            # Execute
            if self.asynchronous:
                job_id = self.backend.run(cancel_old_jobs=cancel_old_jobs, wait=False)
                return self.FunctionReturn(self, job_id)
            else:
                return self.backend.run(cancel_old_jobs=cancel_old_jobs, wait=True)
        finally:
            # Restore original signal handlers
            # In asynchronous mode, we might not want to restore if we return immediately
            # but usually we do because the launcher __call__ returns.
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)

    def _dedent_source(self, source: str) -> str:
        """Dedent source code"""
        lines = source.split("\n")
        if not lines:
            return source

        first_line = lines[0]
        # Skip empty lines at the start
        first_non_empty = next((i for i, line in enumerate(lines) if line.strip()), 0)

        if first_non_empty < len(lines):
            first_line = lines[first_non_empty]
            indent = len(first_line) - len(first_line.lstrip())

            # Deduplicate indentation, but preserve empty lines
            deduplicated_lines = []
            for line in lines:
                if line.strip():  # Non-empty line
                    if len(line) >= indent:
                        deduplicated_lines.append(line[indent:])
                    else:
                        deduplicated_lines.append(line)
                else:  # Empty line
                    deduplicated_lines.append("")
            return "\n".join(deduplicated_lines)

        return source

    def _resolve_dependencies(
        self, func: Callable
    ) -> Tuple[List[str], List[str], bool]:
        """
        Analyze function dependencies and resolve them recursively.
        Returns: (imports_to_add, source_code_to_add, is_safe)
        """
        imports = set()
        sources = []  # List of (name, source) tuples to sort or deduplicate?
        # Actually simple list is fine, but order matters?
        # Dependencies should come before usage?
        # Python functions are late-binding, so order of definition doesn't matter strictly
        # as long as they are defined before CALL.
        # But for variables/classes it might matter.
        # We'll append sources.

        sources_map = {}  # name -> source

        queue = [func]
        processed_funcs = set()  # code objects or funcs

        import inspect

        while queue:
            current_func = queue.pop(0)

            # Use code object for identity if possible, else func object
            func_id = current_func
            if hasattr(current_func, "__code__"):
                func_id = current_func.__code__

            if func_id in processed_funcs:
                continue
            processed_funcs.add(func_id)

            # Closures are still hard. Reject them.
            if hasattr(current_func, "__code__") and current_func.__code__.co_freevars:
                self.logger.debug(
                    f"Function {current_func.__name__} uses closures. Unsafe."
                )
                return [], [], False

            builtin_names = set(dir(builtins))
            global_names = set()

            # Find global names used
            try:
                for instruction in dis.get_instructions(current_func):
                    if instruction.opname == "LOAD_GLOBAL":
                        if instruction.argval not in builtin_names:
                            global_names.add(instruction.argval)
            except Exception as e:
                self.logger.debug(f"Bytecode analysis failed for {current_func}: {e}")
                # If it's the main func, we must fail. If it's a dependency, maybe we can skip?
                # Better fail safe.
                return [], [], False

            # Resolve each name
            for name in global_names:
                # If name is not in globals, it might be a problem
                if (
                    not hasattr(current_func, "__globals__")
                    or name not in current_func.__globals__
                ):
                    # Maybe it's a recursive self-reference?
                    if (
                        hasattr(current_func, "__name__")
                        and name == current_func.__name__
                    ):
                        continue
                    self.logger.debug(f"Global '{name}' not found in function globals.")
                    return [], [], False

                obj = current_func.__globals__[name]

                # Case 1: Module
                if inspect.ismodule(obj):
                    if obj.__name__ == name:
                        imports.add(f"import {name}")
                    else:
                        imports.add(f"import {obj.__name__} as {name}")

                # Case 2: Function (User defined)
                elif inspect.isfunction(obj):
                    if obj not in queue and obj.__code__ not in processed_funcs:
                        try:
                            src = inspect.getsource(obj)
                            sources_map[name] = self._dedent_source(src)
                            queue.append(obj)
                        except:
                            self.logger.debug(
                                f"Could not get source for function '{name}'"
                            )
                            return [], [], False

                # Case 3: Class
                elif inspect.isclass(obj):
                    # We don't recurse into classes yet, just add source
                    if name not in sources_map:
                        try:
                            src = inspect.getsource(obj)
                            sources_map[name] = self._dedent_source(src)
                        except:
                            self.logger.debug(
                                f"Could not get source for class '{name}'"
                            )
                            return [], [], False

                # Case 4: Builtin function/method
                elif inspect.isbuiltin(obj):
                    mod = inspect.getmodule(obj)
                    if mod:
                        if obj.__name__ == name:
                            imports.add(f"from {mod.__name__} import {name}")
                        else:
                            imports.add(
                                f"from {mod.__name__} import {obj.__name__} as {name}"
                            )
                    else:
                        return [], [], False

                else:
                    self.logger.debug(
                        f"Unsupported global object type: {type(obj)} for '{name}'"
                    )
                    return [], [], False

        # Sort imports for consistency
        sorted_imports = sorted(list(imports))
        # Sources
        sorted_sources = list(sources_map.values())

        return sorted_imports, sorted_sources, True

    def __serialize_func_and_args(self, func: Callable = None, args: list = None):
        """Serialize the function and the arguments

        This method uses a simplified serialization strategy:
        - **Always tries dill pickle first** (better performance, handles closures, complex objects)
        - **Falls back to source extraction** only if dill pickle fails
        - With pyenv, Python versions are identical, so dill pickle should always work

        **Fallback to source extraction happens when:**
        - Python versions are incompatible (rare with pyenv)
        - Function is not serializable by dill (built-ins, C functions, etc.)
        - Other serialization errors occur

        **Limitations of source-based serialization:**
        - Functions with closures: Only the function body is captured, not the captured
          variables. The function may fail at runtime if it depends on closure variables.
        - Functions defined in interactive shells or dynamically compiled code may not
          have accessible source.
        - Lambda functions defined inline may have limited source information.

        Args:
            func (Callable, optional): Function to serialize. Defaults to None.
            args (list, optional): Arguments of the function. Defaults to None.
        """
        self.logger.info("Serializing function and arguments...")

        source_extracted = False
        source_method = None
        dill_pickle_used = False
        serialization_method = "dill_pickle"  # Default method

        # Step 1: Always try dill pickle first
        self.logger.info("Attempting dill pickle serialization...")
        try:
            # Try to pickle the function directly with dill
            func_pickle_path = os.path.join(self.project_path, "func.pkl")
            with open(func_pickle_path, "wb") as f:
                dill.dump(func, f)

            # If successful, use pickle
            dill_pickle_used = True
            serialization_method = "dill_pickle"
            self.logger.info("✅ Successfully serialized function with dill pickle.")

            # Clean up any stale source files since we're using dill pickle
            source_path = os.path.join(self.project_path, "func_source.py")
            name_path = os.path.join(self.project_path, "func_name.txt")
            if os.path.exists(source_path):
                os.remove(source_path)
            if os.path.exists(name_path):
                os.remove(name_path)

        except Exception as e:
            # Dill pickle failed - analyze why and fallback to source extraction
            error_type = type(e).__name__
            error_message = str(e)

            # Determine likely reason for failure
            reason_explanation = "Unknown error"
            if "opcode" in error_message.lower() or "bytecode" in error_message.lower():
                reason_explanation = (
                    "Python version incompatibility (bytecode mismatch)"
                )
            elif "cannot pickle" in error_message.lower():
                reason_explanation = (
                    "Function not serializable by dill (built-in, C function, etc.)"
                )
            elif "recursion" in error_message.lower():
                reason_explanation = "Recursion limit reached during serialization"
            else:
                reason_explanation = f"Serialization error: {error_type}"

            self.logger.error(
                f"❌ dill pickle serialization failed: {error_type}: {error_message}"
            )
            self.logger.warning(
                f"⚠️ Falling back to source extraction. Reason: {reason_explanation}"
            )

            dill_pickle_used = False
            serialization_method = "source_extraction"

            # Continue with source extraction below

        # Step 2: Try source extraction if dill pickle failed
        if not dill_pickle_used:
            self.logger.info("📝 Using source extraction fallback (dill pickle failed)")

            # Only analyze dependencies if we need source extraction
            extra_imports, extra_sources, is_safe = self._resolve_dependencies(func)

            if is_safe:
                # Method 1: Try inspect.getsource() (standard library, most common)
                try:
                    source = inspect.getsource(func)
                    source_method = "inspect.getsource"

                    # Combine parts
                    # 1. Imports
                    # 2. Dependency sources
                    # 3. Main function source

                    parts = []
                    if extra_imports:
                        parts.extend(extra_imports)
                        parts.append("")  # newline

                    if extra_sources:
                        parts.extend(extra_sources)
                        parts.append("")  # newline

                    # Dedent main source
                    source = self._dedent_source(source)
                    parts.append(source)

                    final_source = "\n".join(parts)

                    source = final_source
                    source_extracted = True

                except (OSError, TypeError) as e:
                    self.logger.debug(f"inspect.getsource() failed: {e}")
                except Exception as e:
                    self.logger.debug(f"inspect.getsource() unexpected error: {e}")

                # Method 2: Try dill.source.getsource()
                # Note: dill doesn't support our dependency injection easily,
                # so if inspect fails, we might just fallback to pickle.
                # But let's keep it as backup for simple functions.
                if not source_extracted:
                    # BUT we need to be careful. If we use dill source, we miss our injections.
                    # So if imports/sources are needed, we probably shouldn't use raw dill source.
                    # Since is_safe=True implies we resolved dependencies, we EXPECT them to be injected.
                    # If inspect fails, we can't easily combine dill source with our injections reliably
                    # (dill source might have different indentation/structure).
                    # So let's skip dill fallback if we have dependencies.
                    if not extra_imports and not extra_sources:
                        try:
                            if hasattr(dill, "source") and hasattr(
                                dill.source, "getsource"
                            ):
                                source = dill.source.getsource(func)
                                source_method = "dill.source.getsource"
                                source_extracted = True
                        except Exception as e:
                            self.logger.debug(f"dill.source.getsource() failed: {e}")
            else:
                self.logger.warning(
                    "⚠️ Function unsafe for source extraction (unresolvable globals/closures). Will use dill pickle anyway."
                )

        # Process and save source if extracted
        if source_extracted:
            try:
                # Source is already prepared and dedented above if using inspect.
                # If using dill (fallback path), we might need to dedent.
                if source_method == "dill.source.getsource":
                    source = self._dedent_source(source)

                # Save source code
                with open(os.path.join(self.project_path, "func_source.py"), "w") as f:
                    f.write(source)

                # Save function name for loading
                with open(os.path.join(self.project_path, "func_name.txt"), "w") as f:
                    f.write(func.__name__)

                self.logger.info(
                    f"✅ Function source extracted successfully using {source_method}."
                )
                serialization_method = "source_extraction"

            except Exception as e:
                self.logger.warning(f"Failed to process/save function source: {e}")
                source_extracted = False
                # Fallback to dill pickle if source extraction save failed
                serialization_method = "dill_pickle"

        # If source extraction failed or was skipped, ensure no stale source files exist
        if not source_extracted:
            source_path = os.path.join(self.project_path, "func_source.py")
            if os.path.exists(source_path):
                os.remove(source_path)
            
            # Always create func_name.txt even if source extraction failed
            # This is needed for Desi backend queue management
            func_name_path = os.path.join(self.project_path, "func_name.txt")
            if not os.path.exists(func_name_path):
                try:
                    with open(func_name_path, "w") as f:
                        f.write(func.__name__)
                    self.logger.debug(f"Created func_name.txt with function name: {func.__name__}")
                except Exception as e:
                    self.logger.warning(f"Failed to create func_name.txt: {e}")

            # If source extraction was attempted but failed, log it
            if not dill_pickle_used:
                self.logger.warning(
                    "⚠️ Source extraction failed. Using dill pickle as final fallback."
                )
                # Ensure we still pickle the function even if source extraction failed
                serialization_method = "dill_pickle"

        # Always pickle the function (used by dill pickle strategy or as fallback)
        # Create func.pkl if not already created (we created it earlier if dill_pickle_used was True)
        if not dill_pickle_used:
            try:
                func_pickle_path = os.path.join(self.project_path, "func.pkl")
                with open(func_pickle_path, "wb") as f:
                    dill.dump(func, f)
                self.logger.debug(
                    "Created func.pkl as fallback (dill pickle or source extraction fallback)"
                )
            except Exception as e:
                # Only raise if we have no other option (both dill pickle and source extraction failed)
                if not source_extracted:
                    self.logger.error(
                        f"❌ Critical: Failed to pickle function even as fallback: {e}"
                    )
                    raise
                else:
                    # If source extraction succeeded, warn but don't fail
                    self.logger.warning(
                        f"⚠️ Failed to create func.pkl fallback (source extraction will be used): {e}"
                    )

        # Save serialization method indicator
        method_file = os.path.join(self.project_path, "serialization_method.txt")
        with open(method_file, "w") as f:
            f.write(f"{serialization_method}\n")

        # Pickle the arguments
        if args is None:
            args = {}
        with open(os.path.join(self.project_path, "args.pkl"), "wb") as f:
            dill.dump(args, f)


# ---------------------------------------------------------------------------- #
#                             EXAMPLE OF EXECUTION                             #
# ---------------------------------------------------------------------------- #
if __name__ == "__main__":
    import ray
    import torch

    def function_inside_function():
        # Check if file exists before trying to read it, as paths might differ
        if os.path.exists("documentation/RayLauncher.html"):
            with open("documentation/RayLauncher.html", "r") as f:
                return f.read()[0:10]
        return "DocNotFound"

    def example_func(x):
        import time # Encapsulated imports works too !
        print("Waiting for 60 seconds so that you can check the dashboard...")
        time.sleep(60)
        print("Done waiting !")
        result = (
            ray.cluster_resources(),
            f"GPU is available : {torch.cuda.is_available()}",
            x + 1,
            function_inside_function(),
        )
        return result

    cluster = RayLauncher(
        project_name="example",  # Name of the project (will create a directory with this name in the current directory)
        files=["documentation/RayLauncher.html"],  # List of files to push to the server
        use_gpu=True,  # If you need GPU, you can set it to True
        runtime_env={
            "env_vars": {"NCCL_SOCKET_IFNAME": "eno1"}
        },  # Example of environment variable
        server_run=True,  # To run the code on the server and not locally
        cluster="desi",  # Use Desi backend (credentials loaded from .env: DESI_USERNAME and DESI_PASSWORD)
        force_reinstall_venv=False,  # Force reinstall venv to test with Python 3.12.1
        retention_days=1,  # Retain files and venv for 1 day before cleanup
    )

    result = cluster(example_func, args={"x": 5})  # Execute function with arguments
    print(result)
