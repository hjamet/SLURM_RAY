
import os
import sys
from slurmray.backend.desi import DesiBackend
from dataclasses import dataclass

import logging
# Mock Launcher to satisfy DesiBackend
@dataclass
class MockLauncher:
    project_name: str = "maintenance_reset"
    project_path: str = os.getcwd()
    local_python_version: str = "3.12.1"
    logger: logging.Logger = logging.getLogger("Mock")
    
# Setup Logging
logging.basicConfig(level=logging.INFO)
    
def reset_python():
    print("🛠️  RESETTING PYTHON 3.12.1 ON DESI")
    
    # Initialize Backend
    launcher = MockLauncher()
    backend = DesiBackend(launcher)
    
    print("🔌 Connecting...")
    try:
        backend.connect()
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return

    # Command to uninstall
    # We use full path to pyenv as seen in previous logs: /opt/pyenv/bin/pyenv
    # We execute it blindly
    print("🗑️  Uninstalling Python 3.12.1...")
    cmd = "/opt/pyenv/bin/pyenv uninstall -f 3.12.1"
    
    stdin, stdout, stderr = backend.ssh_client.exec_command(cmd)
    
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    
    print(f"STDOUT: {out}")
    if err:
        print(f"STDERR: {err}")
        
    # Verify it's gone
    print("🔍 Verifying removal...")
    stdin, stdout, stderr = backend.ssh_client.exec_command("/opt/pyenv/bin/pyenv versions")
    versions = stdout.read().decode()
    if "3.12.1" not in versions:
        print("✅ Python 3.12.1 successfully removed.")
    else:
        print("⚠️  Python 3.12.1 might still be present (or partially removed).")
        print(versions)

if __name__ == "__main__":
    reset_python()
