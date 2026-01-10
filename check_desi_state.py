import os
import sys
import paramiko
from dotenv import load_dotenv

load_dotenv()

DESI_HOST = os.getenv("DESI_HOST", "130.223.73.209")
DESI_USER = os.getenv("DESI_USERNAME")
DESI_PASS = os.getenv("DESI_PASSWORD")

def check_state():
    if not DESI_USER or not DESI_PASS:
        print("❌ Credentials missing.")
        return

    print(f"🔌 Connecting to Desi ({DESI_HOST})...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(DESI_HOST, username=DESI_USER, password=DESI_PASS)
    
    files = ["/tmp/slurmray_desi_resources.json", "/tmp/slurmray_desi.queue"]
    
    for fpath in files:
        print(f"\n📂 Content of {fpath}:")
        stdin, stdout, stderr = client.exec_command(f"cat {fpath}")
        content = stdout.read().decode().strip()
        if content:
            print(content)
        else:
            print("(empty or file not found)")

    client.close()

if __name__ == "__main__":
    check_state()
