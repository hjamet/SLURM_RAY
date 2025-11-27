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
    """A class that automatically connects RAY workers and executes the function requested by the user"""

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
            files (List[str], optional): List of files to push to the cluster. This path must be **relative** to the project directory. Defaults to [].
            modules (List[str], optional): List of modules to load on the curnagl Cluster. Use `module spider` to see available modules. Defaults to None.
            node_nbr (int, optional): Number of nodes to use. Defaults to 1.
            use_gpu (bool, optional): Use GPU or not. Defaults to False.
            memory (int, optional): Amount of RAM to use per node in GigaBytes. Defaults to 64.
            max_running_time (int, optional): Maximum running time of the job in minutes. Defaults to 60.
            runtime_env (dict, optional): Environment variables to share between all the workers. Can be useful for issues like https://github.com/ray-project/ray/issues/418. Default to empty.
            server_run (bool, optional): If you run the launcher from your local machine, you can use this parameter to execute your function using online cluster ressources. Defaults to True.
            server_ssh (str, optional): If `server_run` is set to true, the addess of the **SLURM** server to use.
            server_username (str, optional): If `server_run` is set to true, the username with which you wish to connect.
            server_password (str, optional): If `server_run` is set to true, the password of the user to connect to the server. CAUTION: never write your password in the code. Defaults to None.
            log_file (str, optional): Path to the log file. Defaults to "logs/RayLauncher.log".
            cluster (str, optional): Type of cluster/backend to use: 'slurm' (default, e.g. Curnagl) or 'desi' (ISIPOL09).
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
        
        self.__setup_logger()
        
        # --- Validation des Arguments ---
        self._validate_arguments()

        self.modules = ["gcc", "python/3.12.1"] + [
            mod for mod in modules if mod not in ["gcc", "python/3.12.1"]
        ]
        if self.use_gpu is True and "cuda" not in self.modules:
            self.modules += ["cuda", "cudnn"]

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

        Args:
            func (Callable, optional): Function to serialize. Defaults to None.
            args (list, optional): Arguments of the function. Defaults to None.
        """
        self.logger.info("Serializing function and arguments...")

        # Pickle the function
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
