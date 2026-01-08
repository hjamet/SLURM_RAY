
import subprocess
from slurmray.RayLauncher import RayLauncher

def check_gpu_info():
    print("Checking NVIDIA Driver info...")
    try:
        result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
    except Exception as e:
        print(f"Failed to run nvidia-smi: {e}")
    return "Done"

if __name__ == "__main__":
    launcher = RayLauncher(
        project_name="desi_driver_check",
        cluster="desi",
        use_gpu=True, # Need GPU allocation implication if any, though Desi is shared
        node_nbr=1
    )
    launcher(check_gpu_info)
