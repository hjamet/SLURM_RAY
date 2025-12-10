# SlurmRay

**SlurmRay** is a powerful tool designed to simplify the execution of Python code on remote clusters (Slurm) and standalone servers. It automates the complex process of dependency management, environment setup, and job submission, allowing you to run your local code on remote resources with a single command.

## Documentation

### RayLauncher

The core class of the package.

```python
from slurmray.RayLauncher import RayLauncher

launcher = RayLauncher(
    project_name="my_project",
    cluster="curnagl", 
    # ... options
)
```

#### Parameters

- **`project_name`** (`str`): Name of the project. A directory with this name will be created on the remote server.
- **`cluster`** (`str`): Target environment.
    - `'curnagl'` (default): Slurm cluster.
    - `'desi'` (or `'isipol'`): Standalone server (ISIPOL09).
    - `'local'`: Run locally (no cluster).
    - Custom IP/Hostname: For custom Slurm clusters.
- **`asynchronous`** (`bool`, default `False`): 
    - `False`: Blocking call. Returns the result of the function.
    - `True`: Non-blocking call. Returns a `FunctionReturn` object immediately.
- **`files`** (`List[str]`): List of additional files to upload (relative paths). Code dependencies are automatically detected, but data files must be listed here.
- **`use_gpu`** (`bool`, default `False`): Request GPU resources.
- **`memory`** (`int`, default `64`): Memory request in GB.
- **`node_nbr`** (`int`, default `1`): Number of nodes.
- **`retention_days`** (`int`, default `7`): Days to keep files on server.
- **`force_reinstall_venv`** (`bool`, default `False`): Force clean environment.

---

### FunctionReturn Object

Returned when `asynchronous=True`.

**Properties:**
- **`result`**: Returns the function result if finished, or `"Compute still in progress"` string.
- **`logs`**: A generator yielding new log lines from the remote execution.

**Methods:**
- **`cancel()`**: Cancels the running job.

---

### Job Cancellation

You can cancel jobs using the `cancel` method on the launcher or the return object.

```python
# Cancel specific job
ret = launcher(func, asynchronous=True)
ret.cancel()

# Cancel last job launched by this launcher
launcher.cancel()

# Cancel specific job by ID or object
launcher.cancel(ret)
launcher.cancel("12345")
```

---

## Usage Examples

### Synchronous (Blocking)

```python
from slurmray.RayLauncher import RayLauncher

def add(a, b):
    return a + b

launcher = RayLauncher(project_name="demo", cluster="desi")
result = launcher(add, args={"a": 1, "b": 2})
print(result) # 3
```

### Asynchronous (Non-Blocking)

```python
import time
from slurmray.RayLauncher import RayLauncher

def long_task(x):
    time.sleep(60)
    return x * x

launcher = RayLauncher(project_name="async_demo", cluster="desi", asynchronous=True)
ret = launcher(long_task, args={"x": 5})

print("Job submitted!")

# Monitor logs
for line in ret.logs:
    print(line)

# Check result
while ret.result == "Compute still in progress":
    time.sleep(5)

print(f"Result: {ret.result}")
```

## Installation

```bash
pip install slurmray
```

### Development

```bash
git clone https://github.com/lopilo/SLURM_RAY.git
cd SLURM_RAY
poetry install
```

## Internal Architecture

- **Dependency Detection**: Scans your function's AST and imports to determine necessary code to upload.
- **Serialization**: Uses `dill` to pickle functions and arguments. Falls back to source extraction if pickling fails.
- **File Sync**: Hashes files to avoid re-uploading unchanged files.
- **Backends**:
    - `SlurmBackend`: Uses `sbatch`, `squeue`, `scancel`.
    - `DesiBackend`: Uses SSH, `nohup`, pid tracking.
    - `LocalBackend`: Uses `subprocess`.

## Contributing

Contributions are welcome! Please follow the steps in `CONTRIBUTING.md`.
