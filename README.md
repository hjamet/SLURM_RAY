# SLURM_RAY

👉[Full documentation](https://www.henri-jamet.com/docs/slurmray/slurm-ray/)

## Description

**SlurmRay** is a module for effortlessly distributing tasks on a [Slurm](https://slurm.schedmd.com/) cluster using the [Ray](https://ray.io/) library. **SlurmRay** was initially designed to work with the [Curnagl](https://wiki.unil.ch/ci/books/high-performance-computing-hpc/page/curnagl) cluster at the *University of Lausanne*. However, it should be able to run on any [Slurm](https://slurm.schedmd.com/) cluster with a minimum of configuration.

## Installation

**SlurmRay** is designed to run both locally and on a cluster without any modification. This design is intended to allow work to be carried out on a local machine until the script seems to be working. It should then be possible to run it using all the resources of the cluster without having to modify the code.

```bash
pip install slurmray
```

## Usage

```python
from slurmray.RayLauncher import RayLauncher
import ray
import torch

def function_inside_function():
    with open("slurmray/RayLauncher.py", "r") as f:
        return f.read()[0:10]

def example_func(x):
    result = (
        ray.cluster_resources(),
        f"GPU is available : {torch.cuda.is_available()}",
        x + 1,
        function_inside_function(),
    )
    return result

launcher = RayLauncher(
    project_name="example", # Name of the project (will create a directory with this name in the current directory)
    func=example_func, # Function to execute
    args={"x": 1}, # Arguments of the function
    files=["slurmray/RayLauncher.py"], # List of files to push to the cluster (file path will be recreated on the cluster)
    modules=[], # List of modules to load on the curnagl Cluster (CUDA & CUDNN are automatically added if use_gpu=True)
    node_nbr=1, # Number of nodes to use
    use_gpu=True, # If you need A100 GPU, you can set it to True
    memory=8, # In MegaBytes
    max_running_time=5, # In minutes
    runtime_env={"env_vars": {"NCCL_SOCKET_IFNAME": "eno1"}}, # Example of environment variable
    server_run=True, # To run the code on the cluster and not locally
    server_ssh="curnagl.dcsr.unil.ch", # Address of the SLURM server
    server_username="hjamet", # Username to connect to the server
    server_password=None, # Will be asked in the terminal
)

result = launcher()
print(result)
```

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

The Launcher documentation is available [here](https://htmlpreview.github.io/?https://raw.githubusercontent.com/hjamet/SLURM_RAY/main/documentation/RayLauncher.html).