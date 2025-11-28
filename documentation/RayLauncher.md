# RayLauncher API Documentation

**RayLauncher** is a module for effortlessly distributing tasks on a [Slurm](https://slurm.schedmd.com/) cluster (like Curnagl) or a standalone server (like ISIPOL09/Desi) using the [Ray](https://ray.io/) library.

## Class `RayLauncher`

A class that automatically connects RAY workers and executes the function requested by the user.

**Official tool from DESI @ HEC UNIL.**

Supports two execution modes:
- **Slurm mode** (`cluster='slurm'`): For Slurm-based clusters like Curnagl. Uses sbatch/squeue for job management.
- **Desi mode** (`cluster='desi'`): For standalone servers like ISIPOL09. Uses Smart Lock scheduling for resource management.

The launcher automatically selects the appropriate backend based on the `cluster` parameter and environment detection.

### Initialization

```python
class RayLauncher(
    project_name: str = None,
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
    cluster: str = "slurm",
    force_reinstall_venv: bool = False,
)
```

#### Arguments

- **project_name** (`str`, optional): Name of the project. Defaults to None.
- **files** (`List[str]`, optional): List of files to push to the cluster/server. This path must be **relative** to the project directory. Defaults to [].
- **modules** (`List[str]`, optional): List of modules to load (Slurm mode only). Use `module spider` to see available modules. Ignored in Desi mode. Defaults to None.
- **node_nbr** (`int`, optional): Number of nodes to use. For Desi mode, this is always 1 (single server). Defaults to 1.
- **use_gpu** (`bool`, optional): Use GPU or not. Defaults to False.
- **memory** (`int`, optional): Amount of RAM to use per node in GigaBytes. For Desi mode, this is not enforced (shared resource). Defaults to 64.
- **max_running_time** (`int`, optional): Maximum running time of the job in minutes. For Desi mode, this is not enforced by a scheduler. Defaults to 60.
- **runtime_env** (`dict`, optional): Environment variables to share between all the workers. Can be useful for issues like https://github.com/ray-project/ray/issues/418. Default to empty.
- **server_run** (`bool`, optional): If you run the launcher from your local machine, you can use this parameter to execute your function using online cluster/server ressources. Defaults to True.
- **server_ssh** (`str`, optional): If `server_run` is set to true, the address of the server to use. Defaults to "curnagl.dcsr.unil.ch" for Slurm mode, or "130.223.73.209" for Desi mode (auto-detected if cluster='desi').
- **server_username** (`str`, optional): If `server_run` is set to true, the username with which you wish to connect. Credentials are automatically loaded from a `.env` file (CURNAGL_USERNAME for Slurm, DESI_USERNAME for Desi) if available. Priority: environment variables → explicit parameter → default ("hjamet" for Slurm, "henri" for Desi).
- **server_password** (`str`, optional): If `server_run` is set to true, the password of the user to connect to the server. Credentials are automatically loaded from a `.env` file (CURNAGL_PASSWORD for Slurm, DESI_PASSWORD for Desi) if available. Priority: explicit parameter → environment variables → interactive prompt. CAUTION: never write your password in the code. Defaults to None.
- **log_file** (`str`, optional): Path to the log file. Defaults to "logs/RayLauncher.log".
- **cluster** (`str`, optional): Type of cluster/backend to use: 'slurm' (default, e.g. Curnagl) or 'desi' (ISIPOL09/Desi server). Defaults to "slurm".
- **force_reinstall_venv** (`bool`, optional): Force complete removal and recreation of virtual environment on remote server/cluster. This will delete the existing venv and reinstall all packages from requirements.txt. Use this if the venv is corrupted or you need a clean installation. Defaults to False.

### Execution

To launch the job, call the instance with the function and its arguments:

```python
result = cluster(func, args={}, cancel_old_jobs=True, serialize=True)
```

- **func** (`Callable`): Function to execute. This function should not be remote but can use ray ressources.
- **args** (`dict`, optional): Arguments of the function. Defaults to {}.
- **cancel_old_jobs** (`bool`, optional): Cancel the old jobs. Defaults to True.
- **serialize** (`bool`, optional): Serialize the function and the arguments. This should be set to False if the function is automatically called by the server. Defaults to True.

### Example

```python
from slurmray.RayLauncher import RayLauncher
import ray
import torch

def example_func(x):
    result = (
        ray.cluster_resources(),
        f"GPU is available : {torch.cuda.is_available()}",
        x + 1,
    )
    return result

cluster = RayLauncher(
    project_name="example",
    files=[],
    node_nbr=1,
    use_gpu=True,
    memory=8,
    max_running_time=5,
    server_run=True,
    cluster="slurm",
)

result = cluster(example_func, args={"x": 5})
print(result)
```

