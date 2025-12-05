# SLURM_RAY

**SLURM_RAY** is a powerful tool designed to simplify the execution of Python code on remote clusters (Slurm) and standalone servers. It automates the complex process of dependency management, environment setup, and job submission, allowing you to run your local code on remote resources with a single command.

## Installation

Prerequisites:
- Python 3.8+
- SSH access to a Slurm cluster or remote server
- [Poetry](https://python-poetry.org/) (recommended for development) or pip

Installation via pip:
```bash
pip install slurmray
```
*Installs the package and its dependencies.*

Installation for development:
```bash
git clone https://github.com/lopilo/SLURM_RAY.git
cd SLURM_RAY
poetry install
```
*Clones the repository and installs dependencies in a virtual environment using Poetry.*

## Key Features

- **Automatic Dependency Management**: Generates optimized `requirements.txt` and handles virtual environment creation on the remote server.
- **Smart Code Synchronization**: Automatically detects and uploads only the necessary local code files based on your function's imports.
- **Incremental Uploads**: Uses file hashing to upload only modified files, saving bandwidth and time.
- **Robust Local Detection**: Distinguishes between installed libraries and local code regardless of virtual environment location or naming.
- **Multi-Backend Support**: Supports Slurm clusters (Curnagl) and standalone servers (Desi/ISIPOL).
- **Seamless Execution**: Serializes your function and arguments, executes them remotely, and retrieves the results.

## Usage Example

```python
from slurmray.RayLauncher import RayLauncher
import ray

def my_func(x):
    return x * x

# Initialize launcher
launcher = RayLauncher(
    project_name="my_project",
    cluster="desi",  # or 'curnagl', 'local', '192.168.1.10'
    use_gpu=True,
    retention_days=1  # Retain files and venv for 1 day before cleanup (1-30 days)
)

# Execute function remotely
result = launcher(my_func, args={"x": 5})
print(result) # 25
```

## Repository Structure

```
root/
├── slurmray/               # Main package source code
│   ├── backend/            # Backend implementations (Slurm, Desi, Local)
│   ├── assets/             # Static assets (scripts, templates)
│   ├── RayLauncher.py      # Main entry point class
│   ├── scanner.py          # Code analysis and dependency detection
│   └── file_sync.py        # File hashing and synchronization
├── tests/                  # Unit and integration tests
├── examples/               # Usage examples
├── documentation/          # Detailed documentation
└── pyproject.toml          # Project configuration and dependencies
```

## Main Entry Points (scripts/)

| Script | Description | Example |
|---|---|---|
| `slurmray/RayLauncher.py` | Main class for programmatic usage. Can be run directly for testing. | `python slurmray/RayLauncher.py` |

## Roadmap

| Task | Objective | State | Dependencies |
|---|---|---|---|
| **Robust Local Detection** | Detect local vs installed packages using `site.getsitepackages` instead of hardcoded paths. | ✅ Done | - |
| **Smart Requirements** | Filter local packages from `requirements.txt` based on installation path to avoid pip errors. | ✅ Done | Robust Local Detection |
| **Incremental Sync** | Implement hash-based file synchronization to upload only changed files. | ✅ Done | - |
| **Recursive Scan** | Detect dependencies by recursively scanning imports starting from the target function. | ✅ Done | - |
