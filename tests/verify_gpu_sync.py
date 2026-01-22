
import os
import time
from slurmray import Cluster

def simple_gpu_check(job_id_suffix):
    """
    Checks GPU availability and sleeps to verify non-regression.
    """
    import torch # Import remotely
    print(f"[{job_id_suffix}] Starting GPU check...")
    
    gpu_available = torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0) if gpu_available else "No GPU"
    device_count = torch.cuda.device_count()
    
    print(f"[{job_id_suffix}] GPU Available: {gpu_available}")
    print(f"[{job_id_suffix}] Device Name: {device_name}")
    print(f"[{job_id_suffix}] Device Count: {device_count}")
    
    # Sleep to simulate work
    time.sleep(5)
    
    return {
        "job_suffix": job_id_suffix,
        "gpu_available": gpu_available,
        "device_name": device_name,
        "device_count": device_count
    }

def run_test():
    # Use a specific test project name to verify locking logic (or lack of crash)
    project_name = "slurmray_verification_GPU_LOCK"
    
    # Initialize launcher
    # Note: ensure you have a .env with credentials or set them implicitly
    # Assuming user env is set up.
    
    print("Launching job 1...")
    launcher1 = Cluster(
        project_name=project_name,
        cluster="desi", # Use Desi as we have credentials
        use_gpu=True,
        node_nbr=1,
        force_reinstall_project=False # Default behavior test
    )
    
    # We want to test logic, but running on cluster might take time.
    # If running locally (server_run=True default), it connects to cluster.
    
    res1 = launcher1(simple_gpu_check, args={"job_id_suffix": "JOB1"})
    print("Result 1:", res1)
    
    print("\nLaunching job 2 (Should use cached environment and NOT re-upload unchanged files)...")
    launcher2 = Cluster(
        project_name=project_name,
        cluster="desi",
        use_gpu=True,
        node_nbr=1,
        force_reinstall_project=False
    )
    res2 = launcher2(simple_gpu_check, args={"job_id_suffix": "JOB2"})
    print("Result 2:", res2)

if __name__ == "__main__":
    run_test()
