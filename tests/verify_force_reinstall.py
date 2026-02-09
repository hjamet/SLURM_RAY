
import os
from slurmray import Cluster

def dummy_func():
    return "OK"

if __name__ == "__main__":
    project_name = "slurmray_verification_FORCE_REINSTALL"
    
    print("Launching with force_reinstall_project=True...")
    launcher = Cluster(
        project_name=project_name,
        cluster="desi",
        num_gpus=0, # Faster, avoid GPU check
        force_reinstall_project=True 
    )
    
    launcher(dummy_func)
    print("Done.")
