
import time
import os
import dill
from slurmray.RayLauncher import RayLauncher

def remote_task(x):
    import time
    print(f"Running on hostname: {os.uname().nodename}")
    print(f"Task with input {x} starting...")
    for i in range(5):
        print(f"Progress {i}/5")
        time.sleep(2) 
    return f"Result from {os.uname().nodename}: {x * 2}"

def verify_desi_async():
    print("Initializing RayLauncher for Desi (Async)...")
    # Must use 'desi' cluster and server_run=True (default implied by cluster='desi' usually, 
    # but let's be explicit if needed. RayLauncher automatically sets server_ssh if cluster='desi')
    
    # We rely on .env for credentials.
    # If not present, this script will fail (interactive prompt/error).
    
    launcher = RayLauncher(
        project_name="desi_async_test",
        cluster="desi",
        asynchronous=True
    )

    print("Launching task...")
    start = time.time()
    ret = launcher(remote_task, args={"x": 50})
    print(f"Launched in {time.time() - start:.2f}s")
    
    print(f"Job ID: {ret.job_id}")
    print(f"Initial status: {ret.result}")

    # Wait loop
    print("Monitoring...")
    while ret.result == "Compute still in progress":
        # Check logs occasionally
        logs = list(ret.logs)
        if logs:
            print(f"Last log: {logs[-1]}")
        else:
            print("No logs yet...")
        time.sleep(5)
    
    print(f"Final Status: {ret.result}")
    
    if "Result from" in str(ret.result):
        print("SUCCESS: Result received from remote.")
    else:
        print("FAILURE: Result unexpected.")

    # Test Cancel
    print("\nTesting Cancel on Desi...")
    print("Launching another task...")
    ret_cancel = launcher(remote_task, args={"x": 100})
    print(f"Launched Job ID: {ret_cancel.job_id}")
    time.sleep(5) # Let it start
    print("Canceling...")
    ret_cancel.cancel()
    print("Cancel command sent.")
    time.sleep(5)
    # Check logs or result - checking result might be stuck or return None or error
    # Because valid result will never appear.
    print("Check if result is still in progress (it should be forever or error out if we check)")
    # Actually if cancelled, subsequent backend.get_result might fail or return None.
    print(f"Result state: {ret_cancel.result}")

if __name__ == "__main__":
    verify_desi_async()
