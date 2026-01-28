
import os
import sys
import subprocess
from slurmray.RayLauncher import Cluster

def diagnostic_task():
    print("="*60)
    print("DIAGNOSTIC TASK RUNNING ON HOST")
    print("="*60)
    
    # 1. Basic Info
    print(f"Python Version: {sys.version}")
    print(f"Executable: {sys.executable}")
    print(f"CWD: {os.getcwd()}")
    
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
        res = subprocess.run([sys.executable, "-m", "venv", "test_venv_diagnostic"], capture_output=True, text=True)
        if res.returncode == 0:
            print("✅ Venv created successfully!")
        else:
            print(f"❌ Venv creation failed with code {res.returncode}")
            print(res.stdout)
            print("STDERR:", res.stderr)
    except Exception as e:
        print(f"Venv creation crashed: {e}")
        
    # 4. Check dependencies (Silent failure investigation)
    print("\nChecking pip list...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "list"], check=False)
    except Exception as e:
        print(f"Pip list failed: {e}")

    return "Diagnostic Complete"

if __name__ == "__main__":
    # Initialize Launcher targeting Desi
    # We use 'desi' cluster mode.
    # We set force_reinstall_project=True to ensure clean code upload.
    # We set force_reinstall_venv=False to test existing venv behavior or we can toggle it.
    
    launcher = Cluster(
        project_name="desi_diagnostic",
        cluster="desi",
        server_run=True,
        log_file=".slogs/diagnostic.log",
        force_reinstall_project=True, # Ensure our diagnostic code is fresh
        files=["scripts/diagnose_desi.py"] # Upload myself
    )
    
    # Run the function
    print("Launching diagnostic job on Desi...")
    res = launcher(diagnostic_task)
    print("Result:", res)
