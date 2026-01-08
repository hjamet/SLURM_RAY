
import os
from slurmray.RayLauncher import RayLauncher

def dummy_func():
    return "OK"

if __name__ == "__main__":
    project_name = "slurmray_verification_FORCE_REINSTALL"
    
    print("Launching with force_reinstall_project=True...")
    launcher = RayLauncher(
        project_name=project_name,
        cluster="desi",
        use_gpu=False, # Faster, avoid GPU check
        node_nbr=1,
        force_reinstall_project=True 
    )
    
    launcher(dummy_func)
    print("Done.")
