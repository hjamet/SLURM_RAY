# SLURM_RAY

👉[Full documentation](https://henri-jamet.vercel.app/cards/documentation/slurm-ray/slurm-ray/)

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
## Launcher documentation

The Launcher documentation is available [here](https://htmlpreview.github.io/?https://raw.githubusercontent.com/hjamet/SLURM_RAY/main/documentation/RayLauncher.html).