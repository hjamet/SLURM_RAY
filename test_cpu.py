"""Test script for CPU execution on cluster"""
import os
from dotenv import load_dotenv
from slurmray.RayLauncher import RayLauncher
import ray

# Load environment variables
load_dotenv()

def hello_world_cpu():
    """Simple hello world function that checks Ray resources"""
    resources = ray.cluster_resources()
    return {
        "message": "Hello World from CPU!",
        "ray_resources": resources,
        "cpu_count": resources.get("CPU", 0)
    }

if __name__ == "__main__":
    username = os.getenv("CURNAGL_USERNAME")
    password = os.getenv("CURNAGL_PASSWORD")
    
    if not username or not password:
        raise ValueError("CURNAGL_USERNAME and CURNAGL_PASSWORD must be set in .env file")
    
    launcher = RayLauncher(
        project_name="test_cpu",
        func=hello_world_cpu,
        args={},
        files=[],
        modules=[],
        node_nbr=1,
        use_gpu=False,
        memory=8,
        max_running_time=5,
        runtime_env={"env_vars": {}},
        server_run=True,
        server_ssh="curnagl.dcsr.unil.ch",
        server_username=username,
        server_password=password,
    )
    
    print("Launching CPU test on cluster...")
    result = launcher()
    print("Result:", result)

