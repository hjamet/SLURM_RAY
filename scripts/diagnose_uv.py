
import os
import sys
import subprocess
from slurmray.RayLauncher import Cluster

def diagnostic_uv():
    print("="*60)
    print(f"DIAGNOSTIC UV (Running on {sys.version.split()[0]})")
    print("="*60)
    
    # 1. Check UV availability
    print("\nChecking for 'uv'...")
    try:
        res = subprocess.run(["uv", "--version"], capture_output=True, text=True)
        if res.returncode == 0:
            print(f"✅ uv found: {res.stdout.strip()}")
        else:
            print("❌ uv NOT found in PATH")
            return "UV Missing"
    except Exception as e:
        print(f"❌ Failed to run uv: {e}")
        return "UV Failed"

    # 2. Try 'uv venv' with Python 3.12 (if available)
    print("\nAttempting 'uv venv' with Python 3.12...")
    venv_path = "uv_test_venv_312"
    
    # Clean previous run
    subprocess.run(["rm", "-rf", venv_path])
    
    try:
        # Assuming we can ask uv to use specific python or it follows pyenv
        # We try to force python 3.12 if pyenv is active, or pass --python 3.12
        cmd = ["uv", "venv", venv_path, "--python", "3.12.1"]
        print(f"Running: {' '.join(cmd)}")
        
        res = subprocess.run(cmd, capture_output=True, text=True)
        print("STDOUT:", res.stdout)
        if res.returncode == 0:
            print("✅ 'uv venv' created successfully!")
            
            # Verify Python inside venv
            venv_python = os.path.join(venv_path, "bin", "python")
            ver_res = subprocess.run([venv_python, "--version"], capture_output=True, text=True)
            print(f"   Venv Python Version: {ver_res.stdout.strip()}")
            
            # Verify Pip availability (uv venv creates pip-less venv? No, it should have pip or rely on uv pip)
            # Actually uv venv often creates a venv compliant with standards.
            # Let's check check pip
            pip_res = subprocess.run([venv_python, "-m", "pip", "--version"], capture_output=True, text=True)
            print(f"   Venv Pip Status: {pip_res.stdout.strip()} (Exit: {pip_res.returncode})")
            
            if pip_res.returncode != 0:
                 print("   ℹ️ Note: 'uv venv' creates venvs without pip by default. We should use 'uv pip install'.")

        else:
            print(f"❌ 'uv venv' creation failed with code {res.returncode}")
            print("STDERR:", res.stderr)
            
    except Exception as e:
        print(f"Venv creation crashed: {e}")

    return "UV Diagnostic Complete"

if __name__ == "__main__":
    launcher = Cluster(
        project_name="desi_uv_diag",
        cluster="desi",
        server_run=True,
        log_file=".slogs/desi_uv.log",
        force_reinstall_project=True, # Clean upload
        files=["scripts/diagnose_uv.py"]
    )
    
    # We don't force local_python_version here, we let it detect or default.
    # The script inside tries to use 3.12 explicitly via uv.
    
    print("Launching UV diagnostic job on Desi...")
    res = launcher(diagnostic_uv)
    print("Result:", res)
