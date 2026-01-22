
import time
import os
import dill
from slurmray import Cluster

def long_sleep(x):
    import time
    print(f"Sleeping for {x} seconds...")
    time.sleep(x)
    return "Finished"

def verify_cancel():
    print("Launching long task...")
    launcher = Cluster(
        project_name="cancel_test",
        asynchronous=True,
        cluster="local"
    )
    
    # Launch task
    ret = launcher(long_sleep, args={"x": 30})
    print("Task launched.")
    
    time.sleep(2)
    print("Canceling task...")
    ret.cancel()
    print("Cancel called.")
    
    time.sleep(2)
    # Check if process is gone?
    # For local backend, log file should verify kill?
    # LocalBackend.cancel checks?
    # Actually LocalBackend.cancel needs to be implemented currently just prints warning in my impl?
    # WAIT, I implemented check but LocalBackend.cancel implementation in `local.py` was NOT updated fully?
    # I updated `run` and `get_result`. Did I update `cancel`?
    # Let's check `LocalBackend.cancel`.
    pass 

if __name__ == "__main__":
    verify_cancel()
