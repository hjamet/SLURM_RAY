#!/usr/bin/env python3
"""
Test hello world GPU pour vérifier que SLURM_RAY fonctionne correctement sur GPU.
Ce test peut être exécuté directement ou via pytest.
"""

from slurmray.RayLauncher import RayLauncher
import ray
import os
from getpass import getpass
from dotenv import load_dotenv

# Try to import torch for GPU availability check
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None


def hello_world_gpu():
    """Fonction simple qui retourne un message et les ressources du cluster avec info GPU."""
    cluster_resources = ray.cluster_resources()
    # Count nodes by counting keys that start with "node:" (excluding internal head)
    node_keys = [key for key in cluster_resources.keys() if key.startswith("node:") and key != "node:__internal_head__"]
    node_count = len(node_keys) if node_keys else 1  # At least 1 node if we have resources
    
    # Check GPU availability
    gpu_available = False
    if TORCH_AVAILABLE and torch is not None:
        gpu_available = torch.cuda.is_available()
    
    # Get GPU count from cluster resources
    gpu_count = int(cluster_resources.get("GPU", 0))
    
    return {
        "message": "Hello World from SLURM_RAY GPU!",
        "cluster_resources": cluster_resources,
        "node_count": node_count,
        "gpu_available": gpu_available,
        "gpu_count": gpu_count,
    }


def test_hello_world_gpu():
    """Test pytest pour hello world GPU."""
    # Load environment variables from .env
    load_dotenv()
    
    # Get credentials from .env or use getpass as fallback
    server_username = os.getenv("CURNAGL_USERNAME")
    server_password = os.getenv("CURNAGL_PASSWORD")
    
    if server_password is None:
        server_password = getpass("Enter your cluster password: ")
    
    cluster = RayLauncher(
        project_name="test_hello_world_gpu",
        files=[],
        modules=[],
        node_nbr=1,
        use_gpu=True,
        memory=8,
        max_running_time=5,
        server_run=True,
        server_ssh="curnagl.dcsr.unil.ch",
        server_username=server_username,
        server_password=server_password,
    )
    
    print("Launching GPU test job...")
    result = cluster(hello_world_gpu, args={})
    
    # Validations
    assert "message" in result, "Result should contain 'message' key"
    assert result["message"] == "Hello World from SLURM_RAY GPU!", f"Expected message, got: {result['message']}"
    assert "cluster_resources" in result, "Result should contain 'cluster_resources' key"
    assert isinstance(result["cluster_resources"], dict), "cluster_resources should be a dictionary"
    assert len(result["cluster_resources"]) > 0, "cluster_resources should not be empty"
    assert "node_count" in result, "Result should contain 'node_count' key"
    assert result["node_count"] > 0, f"node_count should be > 0, got: {result['node_count']}"
    assert "gpu_available" in result, "Result should contain 'gpu_available' key"
    assert isinstance(result["gpu_available"], bool), "gpu_available should be a boolean"
    
    # If GPU is available, verify GPU count
    if result["gpu_available"]:
        assert "gpu_count" in result, "Result should contain 'gpu_count' key"
        assert result["gpu_count"] > 0, f"gpu_count should be > 0 when GPU is available, got: {result['gpu_count']}"
    
    print("\n" + "=" * 50)
    print("GPU Test Results:")
    print("=" * 50)
    print(f"Message: {result['message']}")
    print(f"Node count: {result['node_count']}")
    print(f"GPU available: {result['gpu_available']}")
    print(f"GPU count: {result.get('gpu_count', 0)}")
    print(f"Cluster resources: {result['cluster_resources']}")
    print("\n✅ GPU test completed successfully!")
    
    return result


if __name__ == "__main__":
    test_hello_world_gpu()

