import os
import sys
import paramiko
from dotenv import load_dotenv

load_dotenv()

DESI_HOST = os.getenv("DESI_HOST", "130.223.73.209")
DESI_USER = os.getenv("DESI_USERNAME")
DESI_PASS = os.getenv("DESI_PASSWORD")

def check_locks():
    if not DESI_USER or not DESI_PASS:
        print("❌ Credentials missing.")
        return

    print(f"🔌 Connecting to Desi ({DESI_HOST})...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(DESI_HOST, username=DESI_USER, password=DESI_PASS)
    
    # Check processes
    print("\n🔍 Checking processes matching 'desi' or 'slurmray'...")
    stdin, stdout, stderr = client.exec_command("ps -ef | grep -E 'desi|slurmray' | grep -v grep")
    procs = stdout.read().decode()
    if procs.strip():
        print(procs)
    else:
        print("No active slurmray processes found.")

    # Check lock files status
    locks = ["/tmp/slurmray_desi_resources.lock", "/tmp/slurmray_desi.lock"]
    
    for lock in locks:
        print(f"\n🔐 Checking {lock}...")
        # Check existence
        stdin, stdout, stderr = client.exec_command(f"ls -l {lock}")
        if stdout.channel.recv_exit_status() != 0:
            print(f"   [INFO] File does not exist.")
            continue
            
        print(f"   [INFO] File exists: {stdout.read().decode().strip()}")
        
        # Check flock status via python
        # We pass script via stdin to avoid quoting issues
        check_script = f"""
import fcntl
import sys
import os

lock_file = '{lock}'
try:
    f = open(lock_file, 'w')
    # Try non-blocking exclusive lock
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    print("STATUS: FREE")
    fcntl.flock(f, fcntl.LOCK_UN)
except IOError:
    print("STATUS: LOCKED")
except Exception as e:
    print(f"STATUS: ERROR {{e}}")
"""
        stdin, stdout, stderr = client.exec_command("python3")
        stdin.write(check_script)
        stdin.channel.shutdown_write()
        
        out = stdout.read().decode().strip()
        print(f"   {out}")

    client.close()

if __name__ == "__main__":
    check_locks()
