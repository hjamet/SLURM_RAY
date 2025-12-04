# SLURM_RAY

**Official tool from DESI @ HEC UNIL**

👉[Full documentation](documentation/RayLauncher.md)

## Description

**SlurmRay** is a module for effortlessly distributing tasks on a [Slurm](https://slurm.schedmd.com/) cluster (like Curnagl) or a standalone server (like ISIPOL09/Desi) using the [Ray](https://ray.io/) library. **SlurmRay** was initially designed to work with the [Curnagl](https://wiki.unil.ch/ci/books/high-performance-computing-hpc/page/curnagl) cluster at the *University of Lausanne*. It is now an official tool of the **DESI department @ HEC UNIL** and supports both Slurm-based clusters and direct SSH execution on dedicated servers.

## Installation

**SlurmRay** is designed to run both locally and on a cluster without any modification. This design is intended to allow work to be carried out on a local machine until the script seems to be working. It should then be possible to run it using all the resources of the cluster without having to modify the code.

```bash
pip install slurmray
```

## Prerequisites

### For Slurm clusters (e.g., Curnagl)
- Access to a Slurm cluster with SSH access
- Valid credentials (username/password)
- Python 3.9+ on local machine (Python 3.8+ supported on remote cluster via source serialization)

### For Desi server (ISIPOL09)
- VPN access to the DESI network (if required)
- SSH access to `130.223.73.209`
- Valid credentials (username/password)
- Python 3.9+ on local machine (Python 3.8+ supported on remote server via source serialization)

## Key Results

| Metric | Value | Notes |
|---|---|---|
| Backend Support | Slurm, Desi (SSH) | Curnagl & ISIPOL09 supported |
| Task Management | Ray | Automatic distribution |
| Installation | Optimized | Incremental installation with cache and version detection |
| Dashboard | Integrated | Automatic browser opening (via SSH tunnel) |
| Compatibility | Python 3.9+ (local), Python 3.8+ (remote) | Automatic inter-version serialization handling |

## Repository Structure

```
root/
├── slurmray/               # Package source code
│   ├── backend/            # Backend implementations (Slurm, Desi, Local)
│   ├── assets/             # Script templates (sbatch, spython)
│   └── RayLauncher.py      # Main class
├── tests/                  # Unit and integration tests
├── documentation/          # Project documentation
├── logs/                   # Execution logs
├── poetry.lock             # Locked dependencies
├── pyproject.toml          # Poetry configuration
└── README.md               # Main documentation
```

## Main Entry Scripts (scripts/)

| Path | Description | Example | Explanation |
|---|---|---|---|
| `slurmray/cli.py` | Main CLI interface | `slurmray curnagl` or `slurmray desi` | *Launches the interactive interface to manage jobs and access the dashboard. Supports Curnagl (Slurm) and Desi (ISIPOL09). By default, displays help if no cluster is specified.* |
| `install.sh` | Local installation script | `./install.sh` or `./install.sh --force-reinstall` | *Installs dependencies with Poetry. Use `--force-reinstall` to remove and recreate the local virtual environment before installation.* |

## Secondary Executable Scripts (scripts/utils/)

| Path | Description | Example | Explanation |
|---|---|---|---|
| `tests/test_gpu_dashboard_long.py` | GPU and dashboard test with long job | `poetry run python tests/test_gpu_dashboard_long.py` | *Launches a 5-minute GPU job to test the dashboard via the CLI interface* |
| `tests/test_curnagl_gpu_dashboard.py` | Automated Curnagl test (GPU + Dashboard) | `poetry run python tests/test_curnagl_gpu_dashboard.py` | *Launches a Slurm job with GPU, verifies PyTorch/Ray and local dashboard access via SSH tunnel* |
| `tests/test_desi_gpu_dashboard.py` | Automated Desi test (GPU + Dashboard) | `poetry run python tests/test_desi_gpu_dashboard.py` | *Launches a job on Desi (Smart Lock), verifies PyTorch/Ray and local dashboard access via SSH tunnel* |

## Usage

### Mode 1: Curnagl Cluster (Slurm)

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
    project_name="example_slurm",
    files=[],  # List of files to push to the cluster
    modules=[],  # List of modules to load (CUDA & CUDNN auto-added if use_gpu=True)
    node_nbr=1,  # Number of nodes to use
    use_gpu=True,  # Request GPU resources
    memory=8,  # RAM per node in GB
    max_running_time=5,  # Maximum runtime in minutes
    runtime_env={"env_vars": {"NCCL_SOCKET_IFNAME": "eno1"}},
    server_username="your_username",  # Optional: loaded from CURNAGL_USERNAME if not provided
    server_password=None,  # Optional: loaded from CURNAGL_PASSWORD if not provided, otherwise prompted
    cluster="curnagl",  # Use Curnagl cluster (server_ssh auto-detected to "curnagl.dcsr.unil.ch")
)

# Note: When running with server_run=True, SlurmRay automatically sets up an SSH tunnel 
# to the Ray Dashboard, accessible at http://localhost:8888 during job execution.

result = cluster(example_func, args={"x": 1})
print(result)
```

### Mode 2: Desi Server (ISIPOL09)

```python
from slurmray.RayLauncher import RayLauncher
import ray

def example_func(x):
    result = (
        ray.cluster_resources(),
        x * 2,
    )
    return result

cluster = RayLauncher(
    project_name="example_desi",
    files=[],  # List of files to push to the server
    node_nbr=1,  # Always 1 for Desi (single server)
    use_gpu=False,  # GPU available via Smart Lock
    memory=8,  # Not enforced, shared resource
    max_running_time=30,  # Not enforced by scheduler
    server_username="your_username",  # Optional: loaded from DESI_USERNAME if not provided
    server_password=None,  # Optional: loaded from DESI_PASSWORD if not provided, otherwise prompted
    cluster="desi",  # Use Desi server (server_ssh auto-detected to "130.223.73.209")
)

result = cluster(example_func, args={"x": 21})
print(result)
```

### Mode 3: Local Execution

```python
from slurmray.RayLauncher import RayLauncher
import ray

def example_func(x):
    return ray.cluster_resources(), x * 2

cluster = RayLauncher(
    project_name="example_local",
    cluster="local",  # Force local execution
)

result = cluster(example_func, args={"x": 10})
print(result)
```

### Mode 4: Custom Slurm Cluster (Custom IP)

```python
from slurmray.RayLauncher import RayLauncher
import ray

def example_func(x):
    return ray.cluster_resources(), x + 1

cluster = RayLauncher(
    project_name="example_custom",
    files=[],
    node_nbr=1,
    use_gpu=False,
    memory=8,
    max_running_time=5,
    server_username="your_username",  # Optional: loaded from CURNAGL_USERNAME if not provided
    server_password=None,  # Optional: loaded from CURNAGL_PASSWORD if not provided, otherwise prompted
    cluster="192.168.1.100",  # Custom IP or hostname (uses SlurmBackend)
)

result = cluster(example_func, args={"x": 5})
print(result)
```

### Environment Variables

SlurmRay automatically loads credentials from a `.env` file in your project directory. You can store credentials there to avoid entering them each time:

```bash
# For Curnagl (Slurm)
CURNAGL_USERNAME=your_username
CURNAGL_PASSWORD=your_password

# For Desi (ISIPOL09)
DESI_USERNAME=your_username
DESI_PASSWORD=your_password
```

**Credential loading priority:**
1. **Environment variables** (from `.env` file or system environment) - loaded automatically
2. **Explicit parameters** passed to `RayLauncher()` constructor
3. **Default values** (for username) or **interactive prompt** (for password)

**Note:** The `.env` file should be in your `.gitignore` to avoid committing credentials.

### Force Reinstall Virtual Environment

If you need to force a complete reinstallation of the virtual environment (e.g., due to corruption, version conflicts, or for a clean installation), you can use the `force_reinstall_venv` parameter:

```python
cluster = RayLauncher(
    project_name="example",
    func=example_func,
    args={"x": 1},
    force_reinstall_venv=True,  # Force complete venv recreation
    # ... other parameters
)
```

This will:
- **For remote execution (Slurm/Desi)**: Delete the existing virtual environment on the remote server/cluster and recreate it from scratch, reinstalling all packages from `requirements.txt`
- **For local installation**: Use the `install.sh` script with the `--force-reinstall` flag:

```bash
./install.sh --force-reinstall
```

**Note:** The force reinstall mechanism is safe and will not affect running jobs. The venv is only removed before job execution starts.

### Automatic Cleanup and Retention Scheduling

SlurmRay automatically manages file retention on remote clusters/servers to prevent disk space issues. You can control how long files are retained using the `retention_days` parameter:

```python
cluster = RayLauncher(
    project_name="example",
    retention_days=14,  # Retain files for 14 days (default: 7)
    # ... other parameters
)
```

**How it works:**
- Each job execution updates a retention timestamp on the remote server/cluster
- The `retention_days` parameter (1-30 days) specifies how long project files and venv should be retained
- A cleanup script (`cleanup_old_projects.py`) can be run as a cron job to automatically remove projects that have exceeded their retention period
- This prevents accumulation of old project files while allowing reuse of venv and cache between executions

**Default behavior:**
- Default retention period: **7 days**
- Files are automatically marked with a timestamp on each execution
- The cleanup script must be configured separately on the cluster/server (see `slurmray/assets/cleanup_old_projects.py`)

## Key Differences Between Modes

| Feature | Curnagl Mode | Desi Mode | Local Mode | Custom IP |
|---|---|---|---|---|
| **Cluster parameter** | `cluster="curnagl"` | `cluster="desi"` | `cluster="local"` | `cluster="<ip_or_hostname>"` |
| **Scheduler** | Slurm (sbatch/squeue) | Smart Lock (file-based) | None (local) | Slurm (sbatch/squeue) |
| **Multi-node** | Supported (`node_nbr > 1`) | Single node only | Single node | Supported (`node_nbr > 1`) |
| **Modules** | Supported (`module load`) | Not supported | Not supported | Supported (`module load`) |
| **Memory allocation** | Enforced by Slurm | Shared resource | Local resources | Enforced by Slurm |
| **Time limit** | Enforced by Slurm | Not enforced | Not enforced | Enforced by Slurm |
| **Queue management** | Slurm queue | Smart Lock queue | None | Slurm queue |
| **Default server** | `curnagl.dcsr.unil.ch` | `130.223.73.209` | None | Custom IP/hostname |
| **Credentials** | CURNAGL_USERNAME/PASSWORD | DESI_USERNAME/PASSWORD | None | CURNAGL_USERNAME/PASSWORD |

## Function Serialization and Python Version Compatibility

SlurmRay uses **automatic Python version synchronization via pyenv** and **intelligent serialization strategy** to optimize performance while maintaining compatibility across different Python versions.

### Python Version Management with pyenv

SlurmRay automatically detects your local Python version (from `.python-version` file or `sys.version_info`) and synchronizes it on remote servers using pyenv:

1. **Automatic detection**: Reads `.python-version` file or uses current Python version
2. **pyenv installation**: If pyenv is available on the remote server, SlurmRay automatically installs the matching Python version (if not already installed)
3. **Version activation**: The remote execution uses the same Python version as your local environment
4. **Fallback**: If pyenv is not available, SlurmRay falls back to system Python (modules for Slurm, system Python for Desi) with appropriate warnings

**Note**: pyenv must be installed and accessible on the remote server. If pyenv is not available, SlurmRay will use the system Python and may show compatibility warnings.

### Serialization Strategy

SlurmRay uses a **simplified serialization strategy** that prioritizes performance and reliability:

1. **🔄 Always tries dill pickle first**:
   - Better performance (faster serialization/deserialization)
   - Handles closures, complex objects, and local imports automatically
   - With pyenv, Python versions are identical, so dill pickle should always work
   - More reliable for functions with imports from local projects

2. **⚠️ Falls back to source extraction automatically** if dill pickle fails:
   - Only happens when dill pickle cannot serialize the function
   - Common reasons: Python version incompatibility (rare with pyenv), built-in functions, C functions
   - The function's source code is extracted and saved to `func_source.py`
   - Remote execution runs the source code, avoiding bytecode incompatibilities

### How It Works

1. **Version detection**: Local Python version is detected from `.python-version` or `sys.version_info`
2. **pyenv setup**: On remote server, pyenv installs/activates the matching Python version
3. **Serialization**:
   - **Step 1**: Always tries dill pickle serialization first
   - **Step 2**: If dill pickle fails → automatically falls back to source extraction
   - **Step 3**: If source extraction fails → uses dill pickle anyway (final fallback)
4. **Remote execution**: Function is executed using the synchronized Python version

**Key advantage**: With pyenv ensuring identical Python versions, dill pickle should always work. Source extraction is only used as a fallback for edge cases.

### Limitations

**Source extraction limitations** (only relevant when dill pickle fails):
- Functions with closures: Only the function body is captured, not the captured variables. Functions that depend on closure variables may fail at runtime.
- Functions with global dependencies: Global variables referenced in the function are not automatically included. Ensure all required globals are available on the remote server or pass them as function arguments.
- Built-in functions: Built-in functions (e.g., `len`, `max`) cannot be serialized via source extraction and will fall back to `dill`.

**Dynamically created functions**: Functions created at runtime or in interactive shells may not have accessible source code.

### Best Practices

- **Use `.python-version` file**: Create a `.python-version` file in your project root to explicitly specify the Python version
- **Prefer simple functions**: Functions with minimal dependencies work best
- **Pass dependencies as arguments**: Instead of using closures or globals, pass required values as function arguments
- **Test locally first**: Validate your function works correctly before submitting to the cluster
- **Check logs**: Logs indicate which serialization method is used (🔄 for dill pickle, ⚠️ for source extraction)

## Automatic File Synchronization

SlurmRay automatically synchronizes your project files to the cluster. It uses an intelligent detection strategy to ensure all required code is available remotely:

1.  **Project Files**: All files in your project directory are synchronized (respecting `.gitignore`).
2.  **Editable Packages**: Packages installed in editable mode (`pip install -e .` or Poetry dev dependencies) are automatically detected and their source code is uploaded, even if located outside the project directory.
3.  **Static Analysis**: Your code is scanned to detect local dependencies.
4.  **Dynamic Import Warnings**: SlurmRay warns you if it detects dynamic imports (`importlib`, `__import__`) or file operations with relative paths that might be missing on the cluster. You should add these files manually using the `files=[...]` parameter.

## Tests

The project includes simple "hello world" tests to quickly validate that SLURM_RAY works correctly after major modifications. These tests can be executed directly or via pytest.

### Running tests directly

```bash
# Test CPU
poetry run python tests/test_hello_world_cpu.py

# Test GPU
poetry run python tests/test_hello_world_gpu.py
```

### Running tests with pytest

```bash
# Run all tests
poetry run pytest tests/

# Run specific test
poetry run pytest tests/test_hello_world_cpu.py
poetry run pytest tests/test_hello_world_gpu.py
```

The tests require credentials for the cluster. You can provide them via a `.env` file with `CURNAGL_USERNAME` and `CURNAGL_PASSWORD`, or they will be prompted interactively.

## Publishing to PyPI

This project uses [Poetry](https://python-poetry.org/) for package management and publishing. Follow these steps to publish a new version to PyPI:

### 1. Update the version

Increment the version in `pyproject.toml` according to the type of change:

```bash
# Automatic version bumping
poetry version patch   # 3.6.4 -> 3.6.5 (bugfix)
poetry version minor   # 3.6.4 -> 3.7.0 (new feature)
poetry version major   # 3.6.4 -> 4.0.0 (breaking change)
```

Or manually edit the `version` field in `pyproject.toml`.

### 2. Build the package

```bash
poetry build
```

This creates distribution files in the `dist/` directory:
- `slurmray-{version}.tar.gz` (source distribution)
- `slurmray-{version}-py3-none-any.whl` (wheel)

### 3. Configure PyPI credentials

**First-time setup:**

1. Create an API token on [PyPI](https://pypi.org/manage/account/token/)
2. Configure Poetry to use the token:

```bash
poetry config pypi-token.pypi your-token-here
```

**Alternative:** Poetry will prompt for credentials during publishing. Use `__token__` as username and your API token as password.

### 4. Publish to PyPI

**Production (PyPI):**

```bash
poetry publish
```

**Testing (TestPyPI):**

To test the publishing process without affecting production:

```bash
poetry publish --repository testpypi
```

### Pre-publication checklist

Before publishing, ensure:

- [ ] Version incremented in `pyproject.toml`
- [ ] All tests pass (`poetry run pytest tests/`)
- [ ] README.md is up to date
- [ ] Code tested locally
- [ ] `poetry build` completes without errors
- [ ] PyPI credentials configured

### Quick reference

```bash
# Complete publishing workflow
poetry version patch          # Update version
poetry build                  # Build package
poetry publish                # Publish to PyPI

# Optional: test on TestPyPI first
poetry publish --repository testpypi
```

**Important notes:**

- Each version must be unique on PyPI (versions cannot be overwritten)
- TestPyPI is useful for testing the publishing process
- Consider creating a Git tag after publishing:
  ```bash
  git tag v3.6.5
  git push origin v3.6.5
  ```

## Launcher documentation

The Launcher documentation is available [here](documentation/RayLauncher.md).

# Roadmap

| Task | Objective | Status | Dependencies |
|---|---|---|---|
| **Add auto-refresh functionality to CLI interface** | Implement automatic refresh functionality in the SlurmRay CLI (`slurmray/cli.py`) to automatically update the job status display every 5 seconds without requiring manual user interaction. The implementation must: (1) Modify the interactive CLI loop to refresh the job list and status table automatically at 5-second intervals while maintaining the current interactive menu (Refresh, Cancel Job, Open Dashboard, Quit), (2) Ensure the auto-refresh does not interfere with user input - the refresh should pause when the user is typing or has selected an option, and resume after the action completes, (3) Use a non-blocking approach (threading or async) to update the display in the background while keeping the input prompt responsive, (4) Add a visual indicator (e.g., a timestamp or "Last updated: HH:MM:SS" line) to show when the last refresh occurred, (5) Maintain compatibility with both Slurm (Curnagl) and Desi backends, ensuring the refresh logic works correctly for both job management systems, (6) Handle edge cases gracefully: if a refresh fails (network issue, SSH timeout), log the error but continue the refresh cycle, and display an appropriate warning in the UI, (7) Optionally allow users to disable auto-refresh via a command-line flag or configuration if they prefer manual refresh only. The goal is to provide a real-time monitoring experience similar to `watch` or `htop`, making it easier for users to track job progress without constantly pressing the refresh key. | 📅 To do | - |
| **Optimize Python version management and serialization strategy** | Implement a smart Python version management system using pyenv on remote servers to align Python versions between local and remote environments, and improve the serialization strategy to prioritize dill pickle over source extraction. The implementation must: (1) Detect the local Python version (from `.python-version` or `sys.version_info`) and attempt to install the same version on the remote server using pyenv (check if pyenv is available, install it if needed, then install the matching Python version), (2) Modify the serialization logic in `RayLauncher.__serialize_func_and_args()` to prioritize dill pickle serialization over source extraction when Python versions are compatible, (3) Add clear logging with emoji indicators (e.g., ⚠️ or 🔄) when version incompatibilities force a fallback to source extraction, explicitly showing the local vs remote Python versions and the reason for the fallback, (4) Update both Slurm and Desi backends to support pyenv-based Python version management, (5) Ensure backward compatibility: if pyenv is not available or installation fails, gracefully fall back to the system Python with appropriate warnings, (6) Document the new behavior in the README and update the "Function Serialization" section to reflect the priority order (dill first, source extraction as fallback). The goal is to maximize performance (pickle is faster) while maintaining compatibility across version mismatches. | 📅 To do | - |
| **Integrate Prometheus for Ray metrics monitoring** | Integrate Prometheus into the RayLauncher module to enable monitoring of Ray system and application metrics. Ray automatically exposes Prometheus metrics on each cluster node, but Prometheus must be configured to scrape them. The implementation must: (1) Configure Ray to expose Prometheus metrics by enabling metrics export in `ray start` (via `--metrics-export-port` in `sbatch_template.sh` and equivalent configuration for Desi), (2) Create an automatic discovery mechanism for metrics endpoints using either file-based service discovery (`/tmp/ray/prom_metrics_service_discovery.json`) or HTTP service discovery via the Ray dashboard endpoint `/api/prometheus/sd`, (3) Configure Prometheus to scrape metrics (optionally with auto-discovery via file SD or HTTP SD), (4) Integrate this configuration into Slurm and Desi backends, managing SSH port forwarding to enable local access to Prometheus if necessary, (5) Document usage and configuration in the README and documentation, (6) Optionally integrate Grafana with Ray's default dashboards (available in `/tmp/ray/session_latest/metrics/grafana/dashboards`) for visualization. Metrics must be accessible locally via SSH tunnel similar to the Ray dashboard. This feature must be optional and activatable via a `RayLauncher` constructor parameter (e.g., `enable_prometheus: bool = False`). | 📅 To do | Refactor RayLauncher API to separate configuration and execution |

