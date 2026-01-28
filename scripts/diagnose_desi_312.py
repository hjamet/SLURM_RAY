
import os
import sys
import subprocess
from slurmray.RayLauncher import Cluster

def diagnostic_task():
    print("="*60)
    print("DIAGNOSTIC TASK RUNNING ON HOST (FORCED 3.12.1)")
    print("="*60)
    
    # 1. Basic Info
    print(f"Python Version: {sys.version}")
    print(f"Executable: {sys.executable}")
    
    # 2. Check pyenv permissions (if path is accessible)
    ensurepip_path = "/opt/pyenv/versions/3.12.1/lib/python3.12/ensurepip/_bundled/"
    print(f"\nChecking permissions for {ensurepip_path}...")
    try:
        res = subprocess.run(["ls", "-la", ensurepip_path], capture_output=True, text=True)
        print(res.stdout)
        if res.stderr:
            print("STDERR:", res.stderr)
    except Exception as e:
        print(f"Failed to check permissions: {e}")

    # 3. Attempt Venv Creation (Reproduction of reported bug)
    print("\nAttempting to create venv with system python...")
    try:
        res = subprocess.run([sys.executable, "-m", "venv", "test_venv_diagnostic_312"], capture_output=True, text=True)
        if res.returncode == 0:
            print("✅ Venv created successfully!")
        else:
            print(f"❌ Venv creation failed with code {res.returncode}")
            print(res.stdout)
            print("STDERR:", res.stderr)
    except Exception as e:
        print(f"Venv creation crashed: {e}")

    print("\nChecking Ray/Uvloop versions...")
    subprocess.run([sys.executable, "-m", "pip", "show", "ray", "uvloop", "grpcio"], check=False)

    return "Diagnostic 3.12.1 Complete"

if __name__ == "__main__":
    launcher = Cluster(
        project_name="desi_diagnostic_312",
        cluster="desi",
        server_run=True,
        log_file=".slogs/diagnostic_312.log",
        force_reinstall_project=True, # Ensure clean state
        files=["scripts/diagnose_desi_312.py"]
    )
    
    # FORCE 3.12.1 to reproduce bug
    print("Forcing local_python_version to 3.12.1...")
    launcher.local_python_version = "3.12.1"
    
    # Run the function
    print("Launching diagnostic job on Desi (Forced 3.12.1)...")
    try:
        res = launcher(diagnostic_task)
        print("Result:", res)
    except Exception as e:
        print(f"Job failed as expected: {e}")
