# RayLauncher API Documentation

**RayLauncher** is a module for effortlessly distributing tasks on a [Slurm](https://slurm.schedmd.com/) cluster (like Curnagl) or a standalone server (like ISIPOL09/Desi) using the [Ray](https://ray.io/) library.

## Class `RayLauncher`

A class that automatically connects RAY workers and executes the function requested by the user.

**Official tool from DESI @ HEC UNIL.**

Supports multiple execution modes:
- **Curnagl mode** (`cluster='curnagl'`): For Slurm-based clusters like Curnagl. Uses sbatch/squeue for job management.
- **Desi mode** (`cluster='desi'`): For standalone servers like ISIPOL09. Uses Smart Lock scheduling for resource management.
- **Local mode** (`cluster='local'`): For local execution without remote server/cluster.
- **Custom IP** (`cluster='<ip_or_hostname>'`): For custom Slurm clusters. Uses the provided IP/hostname.

The launcher automatically selects the appropriate backend based on the `cluster` parameter and environment detection.

### Initialization

```python
class RayLauncher(
    project_name: str = None,
    files: List[str] = [],
    modules: List[str] = [],
    node_nbr: int = 1,
    num_gpus: int = 0,
    memory: int = 20,
    num_cpus: int = 4,
    max_running_time: int = 60,
    runtime_env: dict = {"env_vars": {}},
    server_run: bool = True,
    server_ssh: str = None,  # Auto-detected from cluster parameter
    server_username: str = None,
    server_password: str = None,
    log_file: str = "logs/RayLauncher.log",
    cluster: str = "curnagl",  # 'curnagl', 'desi', 'local', or custom IP/hostname
    force_reinstall_venv: bool = False,
    force_reinstall_project: bool = False,
    retention_days: int = 7,
    asynchronous: bool = False,
)
```

#### Arguments

- **project_name** (`str`, optional): Name of the project. Defaults to None.
- **files** (`List[str]`, optional): List of files to push to the cluster/server. This path must be **relative** to the project directory. Defaults to [].
- **modules** (`List[str]`, optional): List of modules to load (Slurm mode only). Use `module spider` to see available modules. Ignored in Desi mode. Defaults to None.
- **node_nbr** (`int`, optional): Number of nodes to use. For Desi mode, this is always 1 (single server). Defaults to 1.
- **num_gpus** (`int`, optional): Number of GPUs to use. Defaults to 0.
- **memory** (`int`, optional): Amount of RAM to use per node in GigaBytes. Defaults to 20.
- **num_cpus** (`int`, optional): Number of CPUs to use per node. Defaults to 4.
- **max_running_time** (`int`, optional): Maximum running time of the job in minutes. For Desi mode, this is not enforced by a scheduler. Defaults to 60.
- **runtime_env** (`dict`, optional): Environment variables to share between all the workers. Can be useful for issues like https://github.com/ray-project/ray/issues/418. Default to empty.
- **server_run** (`bool`, optional): If you run the launcher from your local machine, you can use this parameter to execute your function using online cluster/server ressources. Defaults to True.
- **server_ssh** (`str`, optional): If `server_run` is set to true, the address of the server to use. Auto-detected from `cluster` parameter if not provided. Defaults to None (auto-detected).
- **server_username** (`str`, optional): If `server_run` is set to true, the username with which you wish to connect. Credentials are automatically loaded from a `.env` file (CURNAGL_USERNAME for Curnagl/custom IP, DESI_USERNAME for Desi) if available. Priority: environment variables → explicit parameter → default ("hjamet" for Curnagl/custom IP, "henri" for Desi).
- **server_password** (`str`, optional): If `server_run` is set to true, the password of the user to connect to the server. Credentials are automatically loaded from a `.env` file (CURNAGL_PASSWORD for Curnagl/custom IP, DESI_PASSWORD for Desi) if available. Priority: explicit parameter → environment variables → interactive prompt. CAUTION: never write your password in the code. Defaults to None.
- **log_file** (`str`, optional): Path to the log file. Defaults to "logs/RayLauncher.log".
- **cluster** (`str`, optional): Cluster/server to use: 'curnagl' (default, Slurm cluster), 'desi' (ISIPOL09/Desi server), 'local' (local execution), or a custom IP/hostname (for custom Slurm clusters). Defaults to "curnagl".
- **force_reinstall_venv** (`bool`, optional): Force complete removal and recreation of virtual environment on remote server/cluster. This will delete the existing venv and reinstall all packages from requirements.txt. Use this if the venv is corrupted or you need a clean installation. Defaults to False.
- **force_reinstall_project** (`bool`, optional): Force complete removal of the project directory (excluding logs/venv if possible, but practically cleans the project code) before uploading. Use to ensure a clean state. Defaults to False.
- **retention_days** (`int`, optional): Number of days to retain files and venv on the cluster before automatic cleanup. Must be between 1 and 30 days. Defaults to 7.
- **asynchronous** (`bool`, optional): If True, the call to the function returns immediately with a `FunctionReturn` object. Defaults to False.


### Execution

To launch the job, call the instance with the function and its arguments:

```python
result = cluster(func, args={}, cancel_old_jobs=True, serialize=True)
```

- **func** (`Callable`): Function to execute. This function should not be remote but can use ray ressources.
- **args** (`dict`, optional): Arguments of the function. Defaults to {}.
- **cancel_old_jobs** (`bool`, optional): Cancel the old jobs. Defaults to True.
- **serialize** (`bool`, optional): Serialize the function and the arguments. This should be set to False if the function is automatically called by the server. Defaults to True.

### Example (Desi Mode)

> [!IMPORTANT]
> **Key Best Practices:**
> 1. **Do NOT push source code**: SlurmRay automatically detects and synchronizes your `src` directory and dependencies. Only list datasets, config files, or non-Python resources in the `files` argument.
> 2. **External Launch Script**: Keep your launch script (e.g., `scripts/launch.py`) separate from your actual project code (e.g., in `src/`).
> 3. **Credentials in .env**: Never hardcode passwords. Store `DESI_USERNAME` and `DESI_PASSWORD` in a `.env` file at the root of your project.

```python
# scripts/launch_desi.py
from slurmray.RayLauncher import RayLauncher
from src.my_project.experiment import run_experiment

def main():
    # Initialize the launcher for Desi server
    launcher = RayLauncher(
        project_name="my_desi_experiment",
        # Only push datasets or non-code configs. 
        # Source code is auto-detected and synced!
        files=["data/dataset.json", "config/params.yaml"], 
        num_gpus=1,
        cluster="desi", # Use Desi backend
        force_reinstall_project=True, # Ensure a clean slate for the project code
    )

    # Launch the function
    # The function 'run_experiment' will be executed on the Desi server
    result = launcher(
        run_experiment, 
        args={
            "epochs": 10,
            "batch_size": 32,
            "config_path": "config/params.yaml" # Path relative to project root
        }
    )
    
    print(f"Experiment Result: {result}")

if __name__ == "__main__":
    main()
```

