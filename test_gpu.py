"""Test script for GPU execution on cluster"""
import os
from dotenv import load_dotenv
from slurmray.RayLauncher import RayLauncher
import ray

# Load environment variables
load_dotenv()

def hello_world_gpu():
    """Simple hello world function that checks GPU availability"""
    resources = ray.cluster_resources()
    gpu_available = False
    gpu_count = 0
    
    # Check if GPU is available via Ray resources
    if "GPU" in resources:
        gpu_count = int(resources["GPU"])
        gpu_available = gpu_count > 0
    
    # Try to check with torch if available
    try:
        import torch
        torch_gpu_available = torch.cuda.is_available()
        if torch_gpu_available:
            gpu_count = torch.cuda.device_count()
    except ImportError:
        torch_gpu_available = None
    
    return {
        "message": "Hello World from GPU!",
        "ray_resources": resources,
        "gpu_available": gpu_available,
        "gpu_count": gpu_count,
        "torch_cuda_available": torch_gpu_available if 'torch' in locals() else None
    }

if __name__ == "__main__":
    username = os.getenv("CURNAGL_USERNAME")
    password = os.getenv("CURNAGL_PASSWORD")
    
    if not username or not password:
        raise ValueError("CURNAGL_USERNAME and CURNAGL_PASSWORD must be set in .env file")
    
    launcher = RayLauncher(
        project_name="test_gpu",
        func=hello_world_gpu,
        args={},
        files=[],
        modules=[],
        node_nbr=1,
        use_gpu=True,
        memory=8,
        max_running_time=5,
        runtime_env={"env_vars": {}},
        server_run=True,
        server_ssh="curnagl.dcsr.unil.ch",
        server_username=username,
        server_password=password,
    )
    
    print("Launching GPU test on cluster...")
    result = launcher()
    print("Result:", result)

