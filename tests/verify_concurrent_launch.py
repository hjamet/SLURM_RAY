
import multiprocessing
import time
import os
from slurmray.RayLauncher import RayLauncher

def dummy_task(x):
    import time
    time.sleep(10) # Sleep enough to ensure overlap
    return x * x

def launch_job(job_id):
    print(f"[{job_id}] Launching job...")
    project_name = f"slurmray_verify_concurrent_{job_id}"
    
    # Use Desi cluster to test the Tunnel fix
    launcher = RayLauncher(
        project_name=project_name,
        cluster="desi",
        use_gpu=False,
        node_nbr=1
    )
    
    print(f"[{job_id}] Calling launcher...")
    # Synchronous call returns the result directly
    try:
        res = launcher(dummy_task, args={"x": job_id})
        print(f"[{job_id}] Result: {res}")
        return res
    except Exception as e:
        print(f"[{job_id}] CRASHED: {e}")
        return str(e)

if __name__ == "__main__":
    # Launch 2 jobs concurrently
    p1 = multiprocessing.Process(target=launch_job, args=(5,))
    p2 = multiprocessing.Process(target=launch_job, args=(6,))
    
    p1.start()
    p2.start()
    
    p1.join()
    p2.join()
    
    print("Concurrent test finished. Check output for crashes or success.")
