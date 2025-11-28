import time
import requests
import ray
import concurrent.futures
import threading
import os
from slurmray.RayLauncher import RayLauncher

def job_func(x):
    import time
    import ray
    import torch
    
    # Sleep to allow time for dashboard check (e.g., 2 minutes)
    print("Job started. Sleeping for 120s to allow dashboard check...")
    time.sleep(120)
    
    return (
        ray.cluster_resources(),
        f"GPU is available : {torch.cuda.is_available()}",
        torch.cuda.device_count(),
        torch.cuda.get_device_name(0) if torch.cuda.is_available() else "No GPU",
    )

def test_curnagl_gpu_dashboard():
    print("Initializing RayLauncher for Curnagl...")
    launcher = RayLauncher(
        project_name="test_curnagl_gpu",
        files=[],
        modules=[], 
        node_nbr=1,
        use_gpu=True, # GPU requested
        memory=8,
        max_running_time=10, # 10 mins
        server_run=True,
        server_ssh="curnagl.dcsr.unil.ch",
        # Credentials should be in .env
        cluster="slurm",
    )
    
    # Shared state for dashboard check
    dashboard_status = {"accessible": False, "checked": False}
    
    # Function to monitor dashboard in thread
    def monitor_dashboard():
        print("Monitoring dashboard at http://localhost:8888...")
        start_wait = time.time()
        
        # Poll for up to 5 minutes (or until main thread kills it)
        while time.time() - start_wait < 300:
            try:
                # Try to connect to dashboard
                response = requests.get("http://localhost:8888", timeout=2)
                if response.status_code == 200:
                    print("✅ Dashboard is accessible at http://localhost:8888!")
                    dashboard_status["accessible"] = True
                    break
            except requests.exceptions.ConnectionError:
                pass
            except Exception as e:
                print(f"Unexpected error checking dashboard: {e}")
                
            # Check if we should stop (optional, but thread dies when main ends usually)
            time.sleep(5)
            
        dashboard_status["checked"] = True

    # Run monitor in separate thread
    monitor_thread = threading.Thread(target=monitor_dashboard)
    monitor_thread.daemon = True # Allow main to exit even if this is running
    monitor_thread.start()
    
    # Run launcher (BLOCKING) in main thread
    print("Starting launcher in main thread...")
    try:
        result = launcher(job_func, args={"x": 1})
        print("Job result:", result)
        
        # Verifications
        resources, gpu_avail_str, gpu_count, gpu_name = result
        
        print("\n--- Verifications ---")
        
        # 1. Dashboard
        if dashboard_status["accessible"]:
            print("✅ Dashboard check passed.")
        else:
            print("❌ Dashboard check failed.")
            
        # 2. GPU Availability
        if "True" in gpu_avail_str:
            print(f"✅ GPU is available: {gpu_name}")
        else:
            print(f"❌ GPU is NOT available: {gpu_avail_str}")
            
        # 3. Ray Resources
        if "GPU" in resources and resources["GPU"] > 0:
             print(f"✅ Ray sees {resources['GPU']} GPUs.")
        else:
             print("❌ Ray does not see GPUs in cluster_resources.")
             
    except Exception as e:
        print(f"Launcher failed: {e}")
        raise

if __name__ == "__main__":
    test_curnagl_gpu_dashboard()
