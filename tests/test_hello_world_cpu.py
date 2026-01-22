#!/usr/bin/env python3
"""
Test hello world CPU pour vérifier que SLURM_RAY fonctionne correctement sur CPU.
Ce test peut être exécuté directement ou via pytest.
"""

from slurmray import Cluster
import ray
import os
from getpass import getpass
from dotenv import load_dotenv


def hello_world_cpu():
    """Fonction simple qui retourne un message et les ressources du cluster."""
    cluster_resources = ray.cluster_resources()
    # Count nodes by counting keys that start with "node:" (excluding internal head)
    node_keys = [
        key
        for key in cluster_resources.keys()
        if key.startswith("node:") and key != "node:__internal_head__"
    ]
    node_count = (
        len(node_keys) if node_keys else 1
    )  # At least 1 node if we have resources
    return {
        "message": "Hello World from SLURM_RAY CPU!",
        "cluster_resources": cluster_resources,
        "node_count": node_count,
        "cpu_count": int(cluster_resources.get("CPU", 0)),
    }


def test_hello_world_cpu():
    """Test pytest pour hello world CPU."""
    # Load environment variables from .env
    load_dotenv()

    # Get credentials from .env or use getpass as fallback
    server_username = os.getenv("CURNAGL_USERNAME")
    server_password = os.getenv("CURNAGL_PASSWORD")

    if server_password is None:
        server_password = getpass("Enter your cluster password: ")

    cluster = Cluster(
        project_name="test_hello_world_cpu",
        files=[],
        modules=[],
        node_nbr=1,
        use_gpu=False,
        memory=8,
        max_running_time=5,
        server_username=server_username,
        server_password=server_password,
        cluster="curnagl",  # Use Curnagl cluster
    )

    print("Launching CPU test job...")
    result = cluster(hello_world_cpu, args={})

    # Validations
    assert "message" in result, "Result should contain 'message' key"
    assert (
        result["message"] == "Hello World from SLURM_RAY CPU!"
    ), f"Expected message, got: {result['message']}"
    assert (
        "cluster_resources" in result
    ), "Result should contain 'cluster_resources' key"
    assert isinstance(
        result["cluster_resources"], dict
    ), "cluster_resources should be a dictionary"
    assert len(result["cluster_resources"]) > 0, "cluster_resources should not be empty"
    assert "node_count" in result, "Result should contain 'node_count' key"
    assert (
        result["node_count"] > 0
    ), f"node_count should be > 0, got: {result['node_count']}"
    assert "cpu_count" in result, "Result should contain 'cpu_count' key"
    assert (
        result["cpu_count"] > 0
    ), f"cpu_count should be > 0, got: {result['cpu_count']}"

    print("\n" + "=" * 50)
    print("CPU Test Results:")
    print("=" * 50)
    print(f"Message: {result['message']}")
    print(f"Node count: {result['node_count']}")
    print(f"CPU count: {result['cpu_count']}")
    print(f"Cluster resources: {result['cluster_resources']}")
    print("\n✅ CPU test completed successfully!")

    return result


if __name__ == "__main__":
    test_hello_world_cpu()
