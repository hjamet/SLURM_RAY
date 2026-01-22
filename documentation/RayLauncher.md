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
    server_ssh: str = None,
    server_username: str = None,
    server_password: str = None,
    log_file: str = "logs/RayLauncher.log",
    cluster: str = "curnagl",
    force_reinstall_venv: bool = False,
    force_reinstall_project: bool = False,
    retention_days: int = 7,
    asynchronous: bool = False,
)
```

#### Detailed Arguments

| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| **project_name** | `str` | `None` | **Required.** Name used to identify the project on the remote server. Consistent naming allows for venv reuse. |
| **files** | `List[str]` | `[]` | List of local files/directories to synchronize. **Note:** Python source code imported by your function is automatically detected and pushed; only list non-Python files (data, configs) here. |
| **modules** | `List[str]` | `[]` | Slurm modules to load (e.g., `['gcc/13.2.0', 'python/3.12.1']`). Ignored in Desi mode. |
| **node_nbr** | `int` | `1` | Number of nodes to request. Fixed to 1 for Desi/Local backends. |
| **num_gpus** | `int` | `0` | Number of GPUs to request per node. On Curnagl, this auto-loads CUDA modules. |
| **memory** | `int` | `20` | Amount of RAM in GB to request per node. |
| **num_cpus** | `int` | `4` | Number of CPUs to request per node. |
| **max_running_time** | `int` | `60` | Job time limit in minutes. |
| **runtime_env** | `dict` | `{}` | Ray runtime environment (env vars, etc.). |
| **server_run** | `bool` | `True` | Set to `False` to force local execution. |
| **cluster** | `str` | `'curnagl'` | Target: `'curnagl'`, `'desi'`, `'local'`, or a custom IP. |
| **force_reinstall_venv** | `bool` | `False` | Wipes the remote venv and reinstalls all dependencies from scratch. |
| **force_reinstall_project**| `bool` | `False` | Cleans the remote project directory before uploading. |
| **retention_days** | `int` | `7` | Days to keep files on the server (1-30). Automatic cleanup runs daily. |
| **asynchronous** | `bool` | `False` | If `True`, returns immediately with a `FunctionReturn` tracking object. |

### Execution

To launch the job, call the instance with the function and its arguments:

```python
result = launcher(func, args={}, cancel_old_jobs=True, serialize=True)
```

- **func** (`Callable`): The function to run remotely.
- **args** (`dict`): Arguments for the function.
- **cancel_old_jobs** (`bool`): If `True`, cancels previous jobs for the same project.
- **serialize** (`bool`): Internal use; should be `True`.

### Asynchronous Mode & Tracking

When `asynchronous=True`, the launcher returns a `FunctionReturn` object:

```python
job = launcher(my_function, args={"data": 123})

# Check if finished
if job.result != "Compute still in progress":
    print(f"Final result: {job.result}")

# Monitor logs in real-time
for line in job.logs:
    print(line, end="")

# Cancel the job if needed
job.cancel()
```

### Desi Specifics & Best Practices

1.  **Automatic Dependency Detection**: SlurmRay uses an AST scanner to identify local modules imported by your task. **You do not need to push your source code manually.**
2.  **Import Limitations**: Static imports are handled perfectly. However, **dynamic imports** (using `importlib` or `__import__`) or dynamic file paths in `open()` might not be detected. Add these manually to the `files` list if necessary.
3.  **Venv Reuse**: Remote environments are cached. Using the same `project_name` with the same `requirements.txt` allows for near-instant job startup.
4.  **Log Files**: On Desi, execution logs are stored remotely in `slurmray-server/{project_name}/.slogs/server/`. Use the SlurmRay CLI (`slurmray desi`) to monitor them easily.
5.  **Ray Dashboard**: Access the Ray Dashboard by pressing `Enter` in the SlurmRay CLI and selecting "Open Dashboard". An SSH tunnel will be created automatically.

### Example (Desi Mode)

```python
from slurmray.RayLauncher import RayLauncher
from my_package.core import run_model

def main():
    launcher = RayLauncher(
        project_name="robust_experiment_v1",
        cluster="desi",
        num_gpus=1,
        files=["data/training_set.csv"], # Source code in 'my_package' is auto-detected!
        retention_days=3
    )

    result = launcher(run_model, args={"lr": 0.001})
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
```

## 🐛 Bug Reports & Support

SlurmRay is currently in **beta**. If you identify a bug, please report it on the [GitHub Issues](https://github.com/hjamet/SLURM_RAY/issues) page.

For urgent matters, you can reach out directly to **Henri Jamet** at [henri.jamet@unil.ch](mailto:henri.jamet@unil.ch).
