
import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from slurmray.RayLauncher import RayLauncher

def failing_task():
    print("HELLO FROM REMOTE")
    import sys
    sys.stdout.flush()
    raise ValueError("This is a TEST EXCEPTION to verify traceback visibility.")

if __name__ == "__main__":
    launcher = RayLauncher(
        project_name="error_verification",
        cluster="desi",
        node_nbr=1,
        num_gpus=0,
        # server_password should be loaded automatically from .env
        max_running_time=5
    )
    
    print("Launching failing task (expecting remote traceback in logs)...")
    # We expect this to fail and print the remote traceback to stderr
    launcher(failing_task)
