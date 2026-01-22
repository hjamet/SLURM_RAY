
from slurmray import Cluster
import ray
import os
import time
from dotenv import load_dotenv

def gpu_check_func(x):
    """
    Simple function to verify Ray and GPU access on the remote server.
    It imports libraries inside to avoid serialization issues with external references.
    """
    import sys
    import importlib
    
    # Initialize results
    results = {
        "input_x": x,
        "python_version": sys.version,
        "torch_available": False,
        "cuda_available": False,
        "torch_gpu_count": 0,
        "gpu_names": [],
        "ray_available": False,
        "ray_resources": {},
        "error": None
    }
    
    # Check Torch
    try:
        torch = importlib.import_module("torch")
        results["torch_available"] = True
        if torch.cuda.is_available():
            results["cuda_available"] = True
            results["torch_gpu_count"] = torch.cuda.device_count()
            results["gpu_names"] = [torch.cuda.get_device_name(i) for i in range(results["torch_gpu_count"])]
    except Exception as e:
        results["error"] = f"Torch error: {e}"

    # Check Ray
    try:
        ray = importlib.import_module("ray")
        results["ray_available"] = True
        results["ray_resources"] = ray.cluster_resources()
    except Exception as e:
        err = results.get("error", "")
        results["error"] = f"{err} | Ray error: {e}"

    # Sleep a bit to allow dashboard inspection if needed (optional)
    # time.sleep(10) 
    
    return results

def manual_test_desi_gpu():
    load_dotenv()
    
    print("🚀 Launching Desi GPU & Dashboard Test...")
    print("ℹ️  This test will connect to Desi, request GPU resources, and verify the environment.")

    # Initialize cluster
    cluster = Cluster(
        project_name="test_desi_gpu_dashboard",
        files=[],
        modules=[], # Desi doesn't use modules
        node_nbr=1,
        use_gpu=True, # Request GPU
        memory=4,
        max_running_time=10,
        server_run=True, # Run on server
        server_ssh="130.223.73.209", # Desi IP
        server_username=os.getenv("DESI_USERNAME", "hjamet"), # Default or from env
        server_password=os.getenv("DESI_PASSWORD"), # From env
        cluster="desi" # Desi backend
    )
    
    try:
        result = cluster(gpu_check_func, args={"x": "test_dashboard"})
        print("\n✅ Execution Completed!")
        print("-" * 50)
        print(f"Python Version: {result.get('python_version')}")
        print(f"Torch Available: {result.get('torch_available')}")
        print(f"CUDA Available: {result.get('cuda_available')}")
        print(f"GPU Count: {result.get('torch_gpu_count')}")
        print(f"GPU Names: {result.get('gpu_names')}")
        print(f"Ray Resources: {result.get('ray_resources')}")
        print("-" * 50)
        
        if result.get('cuda_available') and result.get('torch_gpu_count') >= 1:
            print("✅ SUCCESS: GPU detected.")
        else:
            print("⚠️  WARNING: GPU not detected or CUDA unavailable.")
            
        if result.get('error'):
            print(f"⚠️  Remote Errors: {result['error']}")
            
    except Exception as e:
        print(f"❌ Execution failed: {e}")
        raise

if __name__ == "__main__":
    manual_test_desi_gpu()
