
import os
import sys
import subprocess
from slurmray.RayLauncher import Cluster

def diagnostic_segfault():
    print("="*60)
    print(f"SEGFAULT DIAGNOSIS (Python {sys.version.split()[0]})")
    print("="*60)
    
    # Check what is installed
    print("\n📦 PIP LIST:")
    try:
        subprocess.run([sys.executable, "-m", "pip", "list"], check=False)
    except Exception as e:
        print(f"Pip list failed: {e}")
        
    # Check Ray specifically
    try:
        import ray
        print(f"\n✅ Ray Version: {ray.__version__}")
        print(f"   Ray file: {ray.__file__}")
    except ImportError:
        print("\n❌ Ray import failed")

    # Check uvloop
    try:
        import uvloop
        print(f"✅ Uvloop Version: {uvloop.__version__}")
    except ImportError:
        print("ℹ️ Uvloop not installed (good?)")

    return "Segfault Diagnosis Complete"

if __name__ == "__main__":
    launcher = Cluster(
        project_name="desi_ray_diag",
        cluster="desi",
        server_run=True,
        log_file=".slogs/ray_diag.log",
        force_reinstall_project=True,
        files=["scripts/diagnose_ray_segfault.py"]
    )
    
    # Force 3.12.1
    # Note: We must ensure base.py doesn't block it (I reverted the block)
    launcher.local_python_version = "3.12.1"
    
    print("Launching Ray Segfault Diagnosis on Desi...")
    res = launcher(diagnostic_segfault)
    print("Result:", res)
