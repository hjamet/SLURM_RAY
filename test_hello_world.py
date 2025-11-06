#!/usr/bin/env python3
"""
Test simple hello world pour vérifier que les modifications de compatibilité Curnagl fonctionnent.
"""

from slurmray.RayLauncher import RayLauncher
import ray
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


def hello_world():
    """Fonction simple qui retourne un message hello world et les ressources du cluster."""
    return {
        "message": "Hello World from SLURM_RAY!",
        "cluster_resources": ray.cluster_resources(),
        "python_version": ray.__version__ if hasattr(ray, "__version__") else "unknown",
    }


if __name__ == "__main__":
    print("Testing SLURM_RAY with updated Curnagl compatibility...")
    print("Using Python 3.12.1, gcc (latest), cuda (latest), cudnn (latest)")
    print()

    launcher = RayLauncher(
        project_name="test_hello_world",
        func=hello_world,
        args={},
        files=[],
        modules=[],
        node_nbr=1,
        use_gpu=False,
        memory=8,
        max_running_time=5,
        server_run=True,
        server_ssh="curnagl.dcsr.unil.ch",
        server_username=os.getenv("CURNAGL_USERNAME"),
        server_password=os.getenv("CURNAGL_PASSWORD"),
    )

    print("Launching job...")
    result = launcher()
    
    print("\n" + "=" * 50)
    print("Test Results:")
    print("=" * 50)
    print(f"Message: {result['message']}")
    print(f"Python version: {result.get('python_version', 'N/A')}")
    print(f"Cluster resources: {result['cluster_resources']}")
    print("\n✅ Test completed successfully!")

