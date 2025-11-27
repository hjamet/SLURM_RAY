
from slurmray.RayLauncher import RayLauncher
import ray
# import torch # Only imported inside the function
import os
import time
from dotenv import load_dotenv

def gpu_check_func(x):
    import torch
    import ray
    
    resources = ray.cluster_resources()
    gpu_count_torch = torch.cuda.device_count()
    gpu_names = [torch.cuda.get_device_name(i) for i in range(gpu_count_torch)]
    
    return {
        "input_x": x,
        "ray_resources": resources,
        "torch_gpu_count": gpu_count_torch,
        "gpu_names": gpu_names,
        "cuda_available": torch.cuda.is_available()
    }

def manual_test_desi_gpu():
    load_dotenv()
    
    # Check for DESI_PASSWORD
    if not os.environ.get("DESI_PASSWORD"):
        print("⚠️  WARNING: DESI_PASSWORD not found in environment variables.")
        print("You might be prompted for a password.")

    print("🚀 Launching Desi GPU & Dashboard Test...")
    print("ℹ️  This test will:")
    print("   1. Connect to Desi (130.223.73.209)")
    print("   2. Request GPU resources")
    print("   3. Setup an SSH tunnel for the dashboard (check for 'Dashboard accessible at http://localhost:8888' in logs)")
    print("   4. Return GPU info")

    launcher = RayLauncher(
        project_name="test_desi_gpu_dashboard",
        func=gpu_check_func,
        args={"x": "test_dashboard"},
        files=[],
        modules=[], # Desi doesn't use modules
        node_nbr=1,
        use_gpu=True, # Request GPU
        memory=4,
        max_running_time=10,
        server_run=True,
        server_ssh="130.223.73.209",
        server_username="hjamet", # A adapter si besoin, ou charger depuis env? Le code par défaut est hjamet.
        server_password=None, # Will pick up DESI_PASSWORD or prompt
        cluster="desi"
    )
    
    # Override username from env if present for flexibility
    if os.getenv("DESI_USERNAME"):
        launcher.server_username = os.getenv("DESI_USERNAME")
        print(f"ℹ️  Using username from env: {launcher.server_username}")

    try:
        result = launcher()
        print("\n✅ Execution Completed!")
        print("--------------------------------------------------")
        print(f"CUDA Available: {result['cuda_available']}")
        print(f"Torch GPU Count: {result['torch_gpu_count']}")
        print(f"GPU Names: {result['gpu_names']}")
        print(f"Ray Resources: {result['ray_resources']}")
        print("--------------------------------------------------")
        
        if result['torch_gpu_count'] >= 2:
            print("✅ SUCCESS: Detected 2 or more GPUs.")
        else:
            print(f"⚠️  WARNING: Only detected {result['torch_gpu_count']} GPUs (Expected 2).")
            
    except Exception as e:
        print(f"❌ Execution failed: {e}")

if __name__ == "__main__":
    manual_test_desi_gpu()

