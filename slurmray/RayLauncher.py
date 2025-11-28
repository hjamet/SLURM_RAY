from typing import Any, Callable, List
import sys
import os
import dill
import logging
import signal

from slurmray.backend.slurm import SlurmBackend
from slurmray.backend.local import LocalBackend
from slurmray.backend.desi import DesiBackend

dill.settings["recurse"] = True


class RayLauncher:
    """A class that automatically connects RAY workers and executes the function requested by the user.
    
    Official tool from DESI @ HEC UNIL.
    
    Supports two execution modes:
    - **Slurm mode** (`cluster='slurm'`): For Slurm-based clusters like Curnagl. Uses sbatch/squeue for job management.
    - **Desi mode** (`cluster='desi'`): For standalone servers like ISIPOL09. Uses Smart Lock scheduling for resource management.
    
    The launcher automatically selects the appropriate backend based on the `cluster` parameter and environment detection.
    """

    def __init__(
        self,
        project_name: str = None,
        func: Callable = None,
        args: dict = None,
        files: List[str] = [],
        modules: List[str] = [],
        node_nbr: int = 1,
        use_gpu: bool = False,
        memory: int = 64,
        max_running_time: int = 60,
        runtime_env: dict = {"env_vars": {}},
        server_run: bool = True,
        server_ssh: str = "curnagl.dcsr.unil.ch",
        server_username: str = "hjamet",
        server_password: str = None,
        log_file: str = "logs/RayLauncher.log",
        cluster: str = "slurm", # 'slurm' (curnagl) or 'desi'
    ):
        """Initialize the launcher

        Args:
            project_name (str, optional): Name of the project. Defaults to None.
            func (Callable, optional): Function to execute. This function should not be remote but can use ray ressources. Defaults to None.
            args (dict, optional): Arguments of the function. Defaults to None.
            files (List[str], optional): List of files to push to the cluster/server. This path must be **relative** to the project directory. Defaults to [].
            modules (List[str], optional): List of modules to load (Slurm mode only). Use `module spider` to see available modules. Ignored in Desi mode. Defaults to None.
            node_nbr (int, optional): Number of nodes to use. For Desi mode, this is always 1 (single server). Defaults to 1.
            use_gpu (bool, optional): Use GPU or not. Defaults to False.
            memory (int, optional): Amount of RAM to use per node in GigaBytes. For Desi mode, this is not enforced (shared resource). Defaults to 64.
            max_running_time (int, optional): Maximum running time of the job in minutes. For Desi mode, this is not enforced by a scheduler. Defaults to 60.
            runtime_env (dict, optional): Environment variables to share between all the workers. Can be useful for issues like https://github.com/ray-project/ray/issues/418. Default to empty.
            server_run (bool, optional): If you run the launcher from your local machine, you can use this parameter to execute your function using online cluster/server ressources. Defaults to True.
            server_ssh (str, optional): If `server_run` is set to true, the address of the server to use. Defaults to "curnagl.dcsr.unil.ch" for Slurm mode, or "130.223.73.209" for Desi mode (auto-detected if cluster='desi').
            server_username (str, optional): If `server_run` is set to true, the username with which you wish to connect. Defaults to "hjamet" (Slurm) or "henri" (Desi).
            server_password (str, optional): If `server_run` is set to true, the password of the user to connect to the server. Can also be provided via environment variables (CURNAGL_PASSWORD for Slurm, DESI_PASSWORD for Desi). CAUTION: never write your password in the code. Defaults to None.
            log_file (str, optional): Path to the log file. Defaults to "logs/RayLauncher.log".
            cluster (str, optional): Type of cluster/backend to use: 'slurm' (default, e.g. Curnagl) or 'desi' (ISIPOL09/Desi server). Defaults to "slurm".
        """
        # Save the parameters
        self.project_name = project_name
        self.func = func
        self.args = args
        self.files = files
        self.node_nbr = node_nbr
        self.use_gpu = use_gpu
        self.memory = memory
        self.max_running_time = max_running_time
        self.runtime_env = runtime_env
        self.server_run = server_run
        self.server_ssh = server_ssh
        self.server_username = server_username
        self.server_password = server_password
        self.log_file = log_file
        self.cluster_type = cluster.lower() # 'slurm' or 'desi'

        # Set default username if not provided based on cluster type
        if self.server_username == "hjamet" and self.cluster_type == "desi":
            # Try to load from env or use default 'henri' for Desi
            self.server_username = os.getenv("DESI_USERNAME", "henri")
        
        self.__setup_logger()
        
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

        # Create the project directory if not exists
        self.pwd_path = os.getcwd()
        self.module_path = os.path.dirname(os.path.abspath(__file__))
        self.project_path = os.path.join(self.pwd_path, ".slogs", self.project_name)
        if not os.path.exists(self.project_path):
            os.makedirs(self.project_path)
            
        # Initialize Backend
        if self.server_run:
            if self.cluster_type == "desi":
                self.backend = DesiBackend(self)
            elif self.cluster_type == "slurm":
                self.backend = SlurmBackend(self)
            else:
                raise ValueError(f"Unknown cluster type: {self.cluster_type}. Use 'slurm' or 'desi'.")
        elif self.cluster: # Running ON a cluster (Slurm)
             self.backend = SlurmBackend(self)
        else:
             self.backend = LocalBackend(self)

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
        file_handler = logging.FileHandler(self.log_file, mode='w')
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

        # Console handler (only warnings and errors)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

    def _validate_arguments(self):
        """Validate arguments and warn about inconsistencies"""
        if self.cluster_type == "desi":
            # Update default server_ssh if not provided or if it's the default Curnagl one
            if self.server_ssh == "curnagl.dcsr.unil.ch":
                self.logger.info("Switching default server_ssh to Desi IP (130.223.73.209)")
                self.server_ssh = "130.223.73.209"
            
            if self.node_nbr > 1:
                self.logger.warning(f"Warning: Desi cluster only supports single node execution. node_nbr={self.node_nbr} will be ignored (effectively 1).")
            
            if self.modules:
                self.logger.warning("Warning: Modules loading is not supported on Desi (no module system). Modules list will be ignored.")
                
            if self.memory != 64: # Assuming 64 is default
                 self.logger.warning("Warning: Memory allocation is not enforced on Desi (shared resource).")

    def _handle_signal(self, signum, frame):
        """Handle interruption signals (SIGINT, SIGTERM) to cleanup resources"""
        sig_name = signal.Signals(signum).name
        self.logger.warning(f"Signal {sig_name} received. Cleaning up resources...")
        print(f"\nInterruption received ({sig_name}). Canceling job and cleaning up...")
        
        if hasattr(self, 'backend'):
            if hasattr(self.backend, 'job_id') and self.backend.job_id:
                self.backend.cancel(self.backend.job_id)
            elif hasattr(self, 'job_id') and self.job_id: # Fallback if we stored it on launcher
                 self.backend.cancel(self.job_id)
        
        sys.exit(1)

    def __call__(self, cancel_old_jobs: bool = True, serialize: bool = True) -> Any:
        """Launch the job and return the result

        Args:
            cancel_old_jobs (bool, optional): Cancel the old jobs. Defaults to True.
            serialize (bool, optional): Serialize the function and the arguments. This should be set to False if the function is automatically called by the server. Defaults to True.

        Returns:
            Any: Result of the function
        """
        # Register signal handlers
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        try:
            # Serialize function and arguments
            if serialize:
                self.__serialize_func_and_args(self.func, self.args)

            return self.backend.run(cancel_old_jobs=cancel_old_jobs)
        finally:
            # Restore original signal handlers
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)

    def __serialize_func_and_args(self, func: Callable = None, args: list = None):
        """Serialize the function and the arguments
        
        This method attempts to serialize functions using source code extraction
        (via inspect.getsource() or dill.source.getsource()) for better compatibility
        across Python versions. If source extraction fails, it falls back to dill
        bytecode serialization.
        
        **Limitations of source-based serialization:**
        - Functions with closures: Only the function body is captured, not the captured
          variables. The function may fail at runtime if it depends on closure variables.
        - Functions defined in interactive shells or dynamically compiled code may not
          have accessible source.
        - Lambda functions defined inline may have limited source information.
        
        **Fallback behavior:**
        - If source extraction fails, dill bytecode serialization is used as fallback.
        - This ensures backward compatibility but may fail with Python version mismatches.
        
        Args:
            func (Callable, optional): Function to serialize. Defaults to None.
            args (list, optional): Arguments of the function. Defaults to None.
        """
        self.logger.info("Serializing function and arguments...")

        # Try to get source code for the function (more robust across versions)
        source_extracted = False
        source_method = None
        
        # Method 1: Try inspect.getsource() (standard library, most common)
        try:
            import inspect
            source = inspect.getsource(func)
            source_method = "inspect.getsource"
            source_extracted = True
        except (OSError, TypeError) as e:
            # OSError: source code not available (e.g., built-in, C extension)
            # TypeError: not a function or method
            self.logger.debug(f"inspect.getsource() failed: {e}")
        except Exception as e:
            self.logger.debug(f"inspect.getsource() unexpected error: {e}")
        
        # Method 2: Try dill.source.getsource() as alternative
        if not source_extracted:
            try:
                if hasattr(dill, 'source') and hasattr(dill.source, 'getsource'):
                    source = dill.source.getsource(func)
                    source_method = "dill.source.getsource"
                    source_extracted = True
                else:
                    self.logger.debug("dill.source.getsource() not available")
            except Exception as e:
                self.logger.debug(f"dill.source.getsource() failed: {e}")
        
        # Process and save source if extracted
        if source_extracted:
            try:
                # Handle indentation if the function is defined inside another
                # Deduplicate indentation
                lines = source.split('\n')
                if lines:
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
                        source = '\n'.join(deduplicated_lines)
                
                # Save source code
                with open(os.path.join(self.project_path, "func_source.py"), "w") as f:
                    f.write(source)
                
                # Save function name for loading
                with open(os.path.join(self.project_path, "func_name.txt"), "w") as f:
                    f.write(func.__name__)
                
                self.logger.info(f"Function source extracted successfully using {source_method}")
                
            except Exception as e:
                self.logger.warning(f"Failed to process/save function source: {e}")
                source_extracted = False
        else:
            self.logger.warning(
                "Could not extract function source code. "
                "Falling back to dill bytecode serialization. "
                "This may cause issues with Python version mismatches."
            )

        # Always pickle the function (legacy/default method and fallback)
        with open(os.path.join(self.project_path, "func.pkl"), "wb") as f:
            dill.dump(func, f)

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
        result = (
            ray.cluster_resources(),
            f"GPU is available : {torch.cuda.is_available()}",
            x + 1,
            function_inside_function(),
        )
        return result

    launcher = RayLauncher(
        project_name="example",  # Name of the project (will create a directory with this name in the current directory)
        func=example_func,  # Function to execute
        args={"x": 5},  # Arguments of the function
        files=[
            "documentation/RayLauncher.html"
        ] if os.path.exists("documentation/RayLauncher.html") else [],  # List of files to push to the cluster
        modules=[],  # List of modules to load on the curnagl Cluster (CUDA & CUDNN are automatically added if use_gpu=True)
        node_nbr=1,  # Number of nodes to use
        use_gpu=True,  # If you need A100 GPU, you can set it to True
        memory=8,  # In MegaBytes
        max_running_time=5,  # In minutes
        runtime_env={
            "env_vars": {"NCCL_SOCKET_IFNAME": "eno1"}
        },  # Example of environment variable
        server_run=True,  # To run the code on the cluster and not locally
        server_ssh="curnagl.dcsr.unil.ch",  # Address of the SLURM server
        server_username="hjamet",  # Username to connect to the server
        server_password=None,  # Will be asked in the terminal
    )

    result = launcher()
    print(result)
