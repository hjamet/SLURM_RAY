
import os
import sys
from dotenv import load_dotenv
from slurmray.RayLauncher import Cluster

# Load env vars
load_dotenv()

def reset_python():
    print("🛠️  RESETTING PYTHON 3.12.1 ON DESI")
    
    # Initialize Launcher (handles credentials, logging, etc.)
    # We specify backend="desi"
    try:
        launcher = Cluster(
            project_name="maintenance_reset",
            cluster="desi"
        )
    except Exception as e:
        print(f"❌ Launcher init failed: {e}")
        return

    backend = launcher.backend
    
    print("🔌 Connecting...")
    try:
        backend._connect()
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return

    # Command to uninstall
    print("🗑️  Uninstalling Python 3.12.1...")
    cmd = "/opt/pyenv/bin/pyenv uninstall -f 3.12.1"
    
    stdin, stdout, stderr = backend.ssh_client.exec_command(cmd)
    
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    
    print(f"STDOUT: {out}")
    if err:
        print(f"STDERR: {err}")
        
    # Verify
    print("🔍 Verifying removal...")
    stdin, stdout, stderr = backend.ssh_client.exec_command("/opt/pyenv/bin/pyenv versions")
    versions = stdout.read().decode()
    if "3.12.1" not in versions:
        print("✅ Python 3.12.1 successfully removed.")
    else:
        print("⚠️  Python 3.12.1 might still be present.")
        print(versions)

if __name__ == "__main__":
    reset_python()
