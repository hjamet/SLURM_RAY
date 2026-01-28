
import os
import sys
import subprocess
from slurmray.RayLauncher import Cluster

def diagnostic_permissions():
    print("="*60)
    print(f"DIAGNOSTIC PERMISSIONS (Running on {sys.version.split()[0]})")
    print("="*60)
    
    target_path = "/opt/pyenv/versions/3.12.1/lib/python3.12/ensurepip/_bundled/"
    print(f"\nChecking permissions for {target_path}...")
    try:
        # Use ls -laR to see files inside
        res = subprocess.run(["ls", "-laR", target_path], capture_output=True, text=True)
        print(res.stdout)
        if res.stderr:
            print("STDERR (ls):", res.stderr)
    except Exception as e:
        print(f"Failed to check permissions: {e}")

    print("\nAttempting to run python3.12 executable directly...")
    try:
        # Check if python3.12 is available in path or at known location
        python312 = "/opt/pyenv/versions/3.12.1/bin/python3.12"
        res = subprocess.run([python312, "--version"], capture_output=True, text=True)
        print(f"Python 3.12 version check: {res.stdout.strip()} (Exit: {res.returncode})")
        if res.stderr: print("STDERR:", res.stderr)
    except Exception as e:
        print(f"Failed to run python3.12: {e}")

    print("\nAttempting to create venv using python3.12 (subprocess)...")
    try:
        python312 = "/opt/pyenv/versions/3.12.1/bin/python3.12"
        # Create venv in tmp
        venv_path = "/tmp/test_venv_312_subprocess"
        res = subprocess.run([python312, "-m", "venv", venv_path], capture_output=True, text=True)
        if res.returncode == 0:
            print("✅ Venv created successfully with 3.12!")
        else:
            print(f"❌ Venv creation failed with code {res.returncode}")
            print(res.stdout)
            print("STDERR:", res.stderr)
            
            # Check permissions of bundled pip if failed
            if "Permission denied" in res.stderr:
                print("!!! CONFIRMED PERMISSION DENIED !!!")
    except Exception as e:
        print(f"Venv subprocess failed: {e}")

    return "Permissions Logged"

if __name__ == "__main__":
    # Use default python (3.11.6 detected or system)
    # Do NOT set local_python_version to 3.12.1 to avoid Ray trying to run on it.
    launcher = Cluster(
        project_name="desi_perms",
        cluster="desi",
        server_run=True,
        log_file=".slogs/desi_perms.log",
        force_reinstall_project=True,
        files=["scripts/diagnose_desi_permissions.py"]
    )
    
    print("Launching permission diagnostic job on Desi (using safe python)...")
    res = launcher(diagnostic_permissions)
    print("Result:", res)
