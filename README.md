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

if __name__ == "__main__":
    def example_func(x):
        import ray # All packages and resources must be imported inside the function

        return ray.cluster_resources(), x + 1

    launcher = RayLauncher(
        project_name="example",
        func=example_func,
        args={"x": 1},
        modules=[],
        node_nbr=1,
        use_gpu=True,
        memory=64,
        max_running_time=15,
        server_run=True,
        server_ssh="curnagl.dcsr.unil.ch",
        server_username="hjamet",
    )

    result = launcher()
    print(result)
```
