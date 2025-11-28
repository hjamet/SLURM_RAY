import os
import sys
import time
import re
import paramiko
import subprocess
import dill
from typing import Any

from slurmray.backend.remote import RemoteMixin
from slurmray.utils import SSHTunnel, DependencyManager

class DesiBackend(RemoteMixin):
    """Backend for Desi server (ISIPOL09) execution"""
    
    # Constants for Desi environment
    SERVER_BASE_DIR = "/home/users/{username}/slurmray-server" # Need to check where to write on Desi. assuming home.
    PYTHON_CMD = "/usr/bin/python3" # To be verified

    def run(self, cancel_old_jobs: bool = True) -> Any:
        """Run the job on Desi"""
        self._connect()
        
        # Check Python version compatibility
        self._check_python_version_compatibility(self.ssh_client)
        
        sftp = self.ssh_client.open_sftp()
        
        # Base directory on server
        base_dir = f"/home/{self.launcher.server_username}/slurmray-server"
        
        # Generate requirements first to check venv hash
        self._generate_requirements()
        
        # Check if venv can be reused based on requirements hash
        dep_manager = DependencyManager(self.launcher.project_path, self.logger)
        req_file = os.path.join(self.launcher.project_path, "requirements.txt")
        
        should_recreate_venv = True
        if self.launcher.force_reinstall_venv:
            # Force recreation: remove venv if it exists
            self.logger.info("Force reinstall enabled: removing existing virtualenv...")
            self.ssh_client.exec_command(f"rm -rf {base_dir}/venv")
            should_recreate_venv = True
        elif os.path.exists(req_file):
            with open(req_file, 'r') as f:
                req_lines = f.readlines()
            # Check remote hash (if venv exists on remote)
            remote_hash_file = f"{base_dir}/.slogs/venv_hash.txt"
            stdin, stdout, stderr = self.ssh_client.exec_command(f"test -f {remote_hash_file} && cat {remote_hash_file} || echo ''")
            remote_hash = stdout.read().decode('utf-8').strip()
            current_hash = dep_manager.compute_requirements_hash(req_lines)
            
            if remote_hash and remote_hash == current_hash:
                # Hash matches, check if venv exists
                stdin, stdout, stderr = self.ssh_client.exec_command(f"test -d {base_dir}/venv && echo exists || echo missing")
                venv_exists = stdout.read().decode('utf-8').strip() == "exists"
                if venv_exists:
                    should_recreate_venv = False
                    self.logger.info("Virtualenv can be reused (requirements hash matches)")
        
        # Smart cleanup: preserve venv if hash matches
        if should_recreate_venv:
            # Clean up everything including venv
            self.ssh_client.exec_command(f"mkdir -p {base_dir} && rm -rf {base_dir}/*")
            # Create flag file to force venv recreation in script
            if self.launcher.force_reinstall_venv:
                self.ssh_client.exec_command(f"touch {base_dir}/.force_reinstall")
            self.logger.info("Virtualenv will be recreated (requirements changed or missing)")
        else:
            # Clean up everything except venv and cache
            self.ssh_client.exec_command(f"mkdir -p {base_dir} && find {base_dir} -mindepth 1 ! -name 'venv' ! -path '{base_dir}/venv/*' ! -name '.slogs' ! -path '{base_dir}/.slogs/*' -delete")
            # Remove flag file if it exists
            self.ssh_client.exec_command(f"rm -f {base_dir}/.force_reinstall")
            self.logger.info("Preserving virtualenv (requirements unchanged)")
        
        # Generate Python script (spython.py) that will run on Desi
        # This script uses RayLauncher in LOCAL mode (but on the remote machine)
        # We need to adapt spython.py generation to NOT look for sbatch/slurm
        self._write_python_script(base_dir)
        
        # Optimize requirements
        venv_cmd = f"source {base_dir}/venv/bin/activate &&" if not should_recreate_venv else ""
        req_file_to_push = self._optimize_requirements(self.ssh_client, venv_cmd)
        
        # Push files
        self.logger.info("Pushing files to Desi...")
        for file in os.listdir(self.launcher.project_path):
            if file.endswith(".py") or file.endswith(".pkl") or file.endswith(".txt"):
                if file == "requirements.txt":
                    continue
                sftp.put(os.path.join(self.launcher.project_path, file), f"{base_dir}/{file}")
        
        # Push optimized requirements as requirements.txt
        sftp.put(req_file_to_push, f"{base_dir}/requirements.txt")
        
        # Store venv hash on remote for future checks
        if os.path.exists(req_file):
            with open(req_file, 'r') as f:
                req_lines = f.readlines()
            current_hash = dep_manager.compute_requirements_hash(req_lines)
            # Ensure .slogs directory exists on remote
            self.ssh_client.exec_command(f"mkdir -p {base_dir}/.slogs")
            stdin, stdout, stderr = self.ssh_client.exec_command(f"echo '{current_hash}' > {base_dir}/.slogs/venv_hash.txt")
            stdout.channel.recv_exit_status()
            # Also store locally
            dep_manager.store_venv_hash(current_hash)
        
        # Copy source code of slurmray to server (since it's not on PyPI)
        self._push_source_code(sftp, base_dir)
        
        for file in self.launcher.files:
             self._push_file(file, sftp, base_dir)
             
        # Create runner script (shell script to setup env and run python)
        runner_script = "run_desi.sh"
        self._write_runner_script(runner_script, base_dir)
        sftp.put(os.path.join(self.launcher.project_path, runner_script), f"{base_dir}/{runner_script}")
        self.ssh_client.exec_command(f"chmod +x {base_dir}/{runner_script}")
        
        # Run the script
        self.logger.info("Running job on Desi...")
        
        # Smart Lock Logic is implemented inside the runner script or wrapper python?
        # The user asked for "Smart Lock" to be implemented:
        # "Implémenter un système de Scheduling Maison... Le runner doit vérifier un fichier de lock..."
        # It's better to implement this in Python inside the runner script or a wrapper.
        # Let's create a 'desi_wrapper.py' that does the locking then runs 'spython.py'.
        
        desi_wrapper_script = "desi_wrapper.py"
        self._write_desi_wrapper(desi_wrapper_script)
        sftp.put(os.path.join(self.launcher.project_path, desi_wrapper_script), f"{base_dir}/{desi_wrapper_script}")
        
        # Execute
        cmd = f"cd {base_dir} && ./run_desi.sh"
        stdin, stdout, stderr = self.ssh_client.exec_command(cmd, get_pty=True) # get_pty to allow killing?
        
        # Stream output
        job_started = False
        tunnel = None
        
        # Read output
        while True:
            line = stdout.readline()
            if not line:
                break
            print(line, end="")
            self.logger.info(line.strip())
            
            if "Started a local Ray instance" in line or "View the dashboard at" in line:
                job_started = True
                # Start SSH Tunnel
                if not tunnel:
                    self.logger.info("Ray started. Setting up SSH tunnel for dashboard...")
                    try:
                        # Connect to localhost on the remote server (Desi)
                        tunnel = SSHTunnel(
                            ssh_host=self.launcher.server_ssh,
                            ssh_username=self.launcher.server_username,
                            ssh_password=self.launcher.server_password,
                            remote_host="127.0.0.1", 
                            local_port=8888,
                            remote_port=8265,
                            logger=self.logger
                        )
                        tunnel.__enter__()
                        self.logger.info("Dashboard accessible at http://localhost:8888")
                    except Exception as e:
                        self.logger.warning(f"Failed to create SSH tunnel: {e}")
                        tunnel = None
            
        stdout.channel.recv_exit_status()
        
        # Close tunnel
        if tunnel:
            tunnel.__exit__(None, None, None)
        
        # Download result
        self.logger.info("Downloading result...")
        try:
            sftp.get(f"{base_dir}/result.pkl", os.path.join(self.launcher.project_path, "result.pkl"))
            self.logger.info("Result downloaded!")
            
            # Clean up remote temporary files (preserve venv and cache)
            self.logger.info("Cleaning up remote temporary files...")
            self.ssh_client.exec_command(
                f"cd {base_dir} && "
                f"find . -maxdepth 1 -type f \\( -name '*.py' -o -name '*.pkl' -o -name '*.sh' -o -name '*.txt' \\) "
                f"! -name 'requirements.txt' -delete && "
                f"rm -rf .slogs/server 2>/dev/null || true"
            )
            
            # Clean up local temporary files after successful download
            self._cleanup_local_temp_files()
            
        except FileNotFoundError:
             self.logger.error("Result file not found.")
             
        # Load result
        with open(os.path.join(self.launcher.project_path, "result.pkl"), "rb") as f:
            result = dill.load(f)
            
        return result
    
    def _cleanup_local_temp_files(self):
        """Clean up local temporary files after successful execution"""
        temp_files = [
            "func_source.py",
            "func_name.txt",
            "func.pkl",
            "args.pkl",
            "result.pkl",
            "spython.py",
            "run_desi.sh",
            "desi_wrapper.py",
            "requirements_to_install.txt",
        ]
        
        for temp_file in temp_files:
            file_path = os.path.join(self.launcher.project_path, temp_file)
            if os.path.exists(file_path):
                os.remove(file_path)
                self.logger.debug(f"Removed temporary file: {temp_file}")

    def _push_source_code(self, sftp, base_dir):
        """Push local slurmray source code to remote server"""
        self.logger.info("Pushing slurmray source code...")
        source_path = os.path.dirname(self.launcher.module_path) # Parent of slurmray package
        
        # Walk through the slurmray directory
        for root, dirs, files in os.walk(os.path.join(source_path, "slurmray")):
            # Skip __pycache__
            if "__pycache__" in root:
                continue
                
            rel_path = os.path.relpath(root, source_path)
            remote_dir = os.path.join(base_dir, rel_path)
            
            # Create remote directory
            try:
                stdin, stdout, stderr = self.ssh_client.exec_command(f"mkdir -p {remote_dir}")
                stdout.channel.recv_exit_status() # Wait for directory to be created
            except Exception:
                pass
                
            for file in files:
                if file.endswith(".pyc") or file.endswith(".pyo"):
                    continue
                    
                local_file = os.path.join(root, file)
                remote_file = os.path.join(remote_dir, file)
                sftp.put(local_file, remote_file)

    def cancel(self, job_id: str):
        """Cancel job on Desi"""
        # Need to know PID or have a kill file
        pass

    def _write_python_script(self, base_dir):
        """Write the python script (spython.py) that will be executed by the job"""
        self.logger.info("Writing python script...")

        # Remove the old python script
        for file in os.listdir(self.launcher.project_path):
            if file.endswith(".py") and "spython" in file:
                os.remove(os.path.join(self.launcher.project_path, file))

        # Write the python script
        with open(
            os.path.join(self.launcher.module_path, "assets", "spython_template.py"),
            "r",
        ) as f:
            text = f.read()

        text = text.replace("{{PROJECT_PATH}}", f'"{base_dir}"') # On remote, we use absolute path
        
        # Desi is a single machine (or we treat it as such for now). 
        # Ray should run in local mode or with address='auto' but without Slurm specifics.
        # It's basically local execution on a remote machine.
        local_mode = f"\n\tinclude_dashboard=True,\n\tdashboard_host='0.0.0.0',\n\tdashboard_port=8265,\nruntime_env = {self.launcher.runtime_env},\n"
        
        text = text.replace(
            "{{LOCAL_MODE}}",
            local_mode,
        )
        with open(os.path.join(self.launcher.project_path, "spython.py"), "w") as f:
            f.write(text)

    def _write_runner_script(self, filename, base_dir):
        """Write bash script to set up env and run wrapper"""
        content = f"""#!/bin/bash
# Desi Runner Script

# Setup Environment (if needed, e.g. load modules or activate conda)
# Assuming python is available or venv creation

# Check for force reinstall flag
if [ -f ".force_reinstall" ]; then
    echo "Force reinstall flag detected: removing existing virtualenv..."
    rm -rf venv
    rm -f .force_reinstall
fi

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies (only missing ones if venv was preserved)
pip install -r requirements.txt

# Add current directory to PYTHONPATH to make 'slurmray' importable
export PYTHONPATH=$PYTHONPATH:.

# Run Wrapper (Smart Lock + Script)
python3 desi_wrapper.py
"""
        with open(os.path.join(self.launcher.project_path, filename), "w") as f:
            f.write(content)

    def _write_desi_wrapper(self, filename):
        """Write python wrapper for Smart Lock"""
        content = f"""
import os
import sys
import time
import fcntl
import subprocess

LOCK_FILE = "/tmp/slurmray_desi.lock"
MAX_RETRIES = 1000
RETRY_DELAY = 30 # seconds

def acquire_lock():
    print("Acquiring lock...")
    lock_fd = open(LOCK_FILE, 'w')
    try:
        # Try to acquire non-blocking exclusive lock
        fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print("Lock acquired!")
        return lock_fd
    except IOError:
        return None

def main():
    print("Starting Smart Lock Scheduler...")
    
    lock_fd = None
    retries = 0
    
    while lock_fd is None:
        lock_fd = acquire_lock()
        if lock_fd is None:
            print(f"Resources busy. Waiting... (Attempt {{retries + 1}})")
            time.sleep(RETRY_DELAY)
            retries += 1
            
    # Lock acquired, run payload
    try:
        print("Starting Payload (spython.py)...")
        subprocess.check_call([sys.executable, "spython.py"])
    finally:
        # Release lock
        print("Releasing lock...")
        fcntl.lockf(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
        print("Lock released.")

if __name__ == "__main__":
    main()
"""
        with open(os.path.join(self.launcher.project_path, filename), "w") as f:
            f.write(content)
