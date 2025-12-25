
from slurmray.RayLauncher import RayLauncher
from slurmray.backend.desi import DesiBackend
from dotenv import load_dotenv
import os

load_dotenv()

def debug_fs():
    print("Connecting to Desi...")
    launcher = RayLauncher(project_name="desi_async_test", cluster="desi")
    # Access backend directly
    backend = launcher.backend
    backend._connect()
    
    username = launcher.server_username
    print(f"Username: {username}")
    
    paths_to_check = [
        f"/home/{username}/slurmray-server/desi_async_test",
        f"/home/{username}/slurmray_desi/desi_async_test",
        f"/home/users/{username}/slurmray-server/desi_async_test"
    ]
    
    sftp = backend.get_sftp()
    
    for path in paths_to_check:
        print(f"Checking path: {path}")
        try:
            files = sftp.listdir(path)
            print(f"✅ Found {len(files)} files: {files}")
        except FileNotFoundError:
            print("❌ Path not found")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    debug_fs()
