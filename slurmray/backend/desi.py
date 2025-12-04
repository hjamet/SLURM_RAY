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
    SERVER_BASE_DIR = "/home/users/{username}/slurmray-server"  # Need to check where to write on Desi. assuming home.
    PYTHON_CMD = "/usr/bin/python3"  # To be verified

    def __init__(self, launcher):
        super().__init__(launcher)
        self.tunnel = None

    def run(self, cancel_old_jobs: bool = True) -> Any:
        """Run the job on Desi"""
        self.logger.info("🔌 Connecting to Desi server...")
        self._connect()
        self.logger.info("✅ Connected successfully")

        # Setup pyenv Python version if available
        self.pyenv_python_cmd = None
        if hasattr(self.launcher, "local_python_version"):
            self.pyenv_python_cmd = self._setup_pyenv_python(
                self.ssh_client, self.launcher.local_python_version
            )

        # Check Python version compatibility (with pyenv if available)
        is_compatible = self._check_python_version_compatibility(
            self.ssh_client, self.pyenv_python_cmd
        )
        self.python_version_compatible = is_compatible

        sftp = self.ssh_client.open_sftp()

        # Base directory on server (organized by project name)
        base_dir = f"/home/{self.launcher.server_username}/slurmray-server/{self.launcher.project_name}"

        # Generate requirements first to check venv hash
        self._generate_requirements()

        # Check if venv can be reused based on requirements hash
        dep_manager = DependencyManager(self.launcher.project_path, self.logger)
        req_file = os.path.join(self.launcher.project_path, "requirements.txt")

        should_recreate_venv = True
        if self.launcher.force_reinstall_venv:
            # Force recreation: remove venv if it exists
            self.logger.info("🔄 Recreating virtual environment...")
            self.ssh_client.exec_command(f"rm -rf {base_dir}/venv")
            should_recreate_venv = True
        elif os.path.exists(req_file):
            with open(req_file, "r") as f:
                req_lines = f.readlines()
            # Check remote hash (if venv exists on remote)
            remote_hash_file = f"{base_dir}/.slogs/venv_hash.txt"
            stdin, stdout, stderr = self.ssh_client.exec_command(
                f"test -f {remote_hash_file} && cat {remote_hash_file} || echo ''"
            )
            remote_hash = stdout.read().decode("utf-8").strip()
            current_hash = dep_manager.compute_requirements_hash(req_lines)

            if remote_hash and remote_hash == current_hash:
                # Hash matches, check if venv exists
                stdin, stdout, stderr = self.ssh_client.exec_command(
                    f"test -d {base_dir}/venv && echo exists || echo missing"
                )
                venv_exists = stdout.read().decode("utf-8").strip() == "exists"
                if venv_exists:
                    should_recreate_venv = False

        # Smart cleanup: preserve venv if hash matches
        if should_recreate_venv:
            # Clean up everything including venv
            self.ssh_client.exec_command(f"mkdir -p {base_dir} && rm -rf {base_dir}/*")
            # Create flag file to force venv recreation in script
            if self.launcher.force_reinstall_venv:
                self.ssh_client.exec_command(f"touch {base_dir}/.force_reinstall")
        else:
            # Clean up everything except venv and cache
            self.ssh_client.exec_command(
                f"mkdir -p {base_dir} && find {base_dir} -mindepth 1 ! -name 'venv' ! -path '{base_dir}/venv/*' ! -name '.slogs' ! -path '{base_dir}/.slogs/*' -delete"
            )
            # Remove flag file if it exists
            self.ssh_client.exec_command(f"rm -f {base_dir}/.force_reinstall")

        # Generate Python script (spython.py) that will run on Desi
        # This script uses RayLauncher in LOCAL mode (but on the remote machine)
        # We need to adapt spython.py generation to NOT look for sbatch/slurm
        self._write_python_script(base_dir)

        # Optimize requirements
        venv_cmd = (
            f"source {base_dir}/venv/bin/activate &&"
            if not should_recreate_venv
            else ""
        )
        req_file_to_push = self._optimize_requirements(self.ssh_client, venv_cmd)

        # Push files
        files_to_push = [
            f
            for f in os.listdir(self.launcher.project_path)
            if (f.endswith(".py") or f.endswith(".pkl") or f.endswith(".txt"))
            and f != "requirements.txt"
        ]
        if files_to_push:
            self.logger.info(f"📤 Uploading {len(files_to_push)} file(s) to server...")
            for file in files_to_push:
                sftp.put(
                    os.path.join(self.launcher.project_path, file), f"{base_dir}/{file}"
                )

        # Push optimized requirements as requirements.txt
        if os.path.exists(req_file_to_push):
            sftp.put(req_file_to_push, f"{base_dir}/requirements.txt")
        else:
            # Ensure no stale requirements.txt exists on remote if local one is missing
            try:
                sftp.remove(f"{base_dir}/requirements.txt")
            except IOError:
                pass  # File didn't exist

        # Store venv hash on remote for future checks
        if os.path.exists(req_file):
            with open(req_file, "r") as f:
                req_lines = f.readlines()
            current_hash = dep_manager.compute_requirements_hash(req_lines)
            # Ensure .slogs directory exists on remote
            self.ssh_client.exec_command(f"mkdir -p {base_dir}/.slogs")
            stdin, stdout, stderr = self.ssh_client.exec_command(
                f"echo '{current_hash}' > {base_dir}/.slogs/venv_hash.txt"
            )
            stdout.channel.recv_exit_status()
            # Also store locally
            dep_manager.store_venv_hash(current_hash)

        # Update retention timestamp
        self._update_retention_timestamp(
            self.ssh_client, base_dir, self.launcher.retention_days
        )

        # Copy source code of slurmray to server (since it's not on PyPI)
        self.logger.info("📦 Uploading slurmray source code...")
        self._push_source_code(sftp, base_dir)

        for file in self.launcher.files:
            self._push_file(file, sftp, base_dir)

        # Create runner script (shell script to setup env and run python)
        runner_script = "run_desi.sh"
        self._write_runner_script(runner_script, base_dir)
        sftp.put(
            os.path.join(self.launcher.project_path, runner_script),
            f"{base_dir}/{runner_script}",
        )
        self.ssh_client.exec_command(f"chmod +x {base_dir}/{runner_script}")

        # Run the script
        self.logger.info("🚀 Starting job execution...")

        desi_wrapper_script = "desi_wrapper.py"
        self._write_desi_wrapper(desi_wrapper_script)
        sftp.put(
            os.path.join(self.launcher.project_path, desi_wrapper_script),
            f"{base_dir}/{desi_wrapper_script}",
        )

        # Execute
        cmd = f"cd {base_dir} && ./run_desi.sh"
        stdin, stdout, stderr = self.ssh_client.exec_command(cmd, get_pty=True)

        # Stream output
        ray_started = False

        # Read output line by line
        while True:
            line = stdout.readline()
            if not line:
                break

            # Filter out noisy messages and format nicely
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Skip pkill errors (already handled silently)
            if "pkill:" in line_stripped:
                continue

            # Detect Ray startup
            if (
                "Started a local Ray instance" in line_stripped
                or "View the dashboard at" in line_stripped
            ) and not ray_started:
                ray_started = True
                # Extract dashboard URL if present
                if "http://" in line_stripped:
                    # Extract URL from line
                    import re

                    url_match = re.search(r"http://[^\s]+", line_stripped)
                    if url_match:
                        dashboard_url = url_match.group(0)
                        self.logger.info(f"📊 Ray dashboard started at {dashboard_url}")

                # Start SSH Tunnel
                if not self.tunnel:
                    try:
                        self.tunnel = SSHTunnel(
                            ssh_host=self.launcher.server_ssh,
                            ssh_username=self.launcher.server_username,
                            ssh_password=self.launcher.server_password,
                            remote_host="127.0.0.1",
                            local_port=8888,
                            remote_port=8265,
                            logger=self.logger,
                        )
                        self.tunnel.__enter__()
                        self.logger.info(
                            "🌐 Dashboard accessible locally at http://localhost:8888"
                        )
                    except Exception as e:
                        self.logger.warning(f"⚠️  Could not establish SSH tunnel: {e}")
                        self.tunnel = None
                continue

            # Print all output (user's print statements and important messages)
            # Filter out only very noisy system messages
            if not any(noise in line_stripped for noise in ["pkill:", "WARNING:"]):
                # Always print user output
                print(line, end="", flush=True)

                # Log important system messages with emojis
                if (
                    "Error" in line_stripped
                    or "Traceback" in line_stripped
                    or "Exception" in line_stripped
                ):
                    self.logger.error(f"❌ {line_stripped}")
                elif "Lock acquired" in line_stripped:
                    self.logger.info(f"🔒 {line_stripped}")
                elif "Starting Payload" in line_stripped:
                    self.logger.info(f"🚀 {line_stripped}")
                elif "Loaded function" in line_stripped:
                    self.logger.info(f"📦 {line_stripped}")
                elif "Job started" in line_stripped or "Sleeping" in line_stripped:
                    self.logger.info(f"▶️  {line_stripped}")
                elif "Result written" in line_stripped:
                    self.logger.info(f"💾 {line_stripped}")
                elif (
                    "Releasing lock" in line_stripped
                    or "Lock released" in line_stripped
                ):
                    self.logger.info(f"🔓 {line_stripped}")

        # Read any remaining stderr
        stderr_output = stderr.read().decode("utf-8")
        if stderr_output.strip():
            self.logger.error(f"Script errors:\n{stderr_output}")
            print(stderr_output, end="")

        exit_status = stdout.channel.recv_exit_status()

        # Check if script failed - fail-fast immediately
        if exit_status != 0:
            # Collect error information
            error_msg = f"Job script exited with non-zero status: {exit_status}"
            if stderr_output.strip():
                error_msg += f"\nScript errors:\n{stderr_output}"

            # Log the error
            self.logger.error(error_msg)

            # Close tunnel if open
            if self.tunnel:
                try:
                    self.tunnel.__exit__(None, None, None)
                except Exception:
                    pass
                self.tunnel = None

            # Raise exception immediately (fail-fast)
            raise RuntimeError(error_msg)

        # Wait a bit for file system to sync
        # Keep tunnel open during job execution - it will be closed at the end of run()
        time.sleep(2)

        # Wait for result file to be created on remote (with timeout)
        self.logger.info("⏳ Waiting for job completion...")
        max_wait = 300  # 5 minutes max
        wait_start = time.time()
        result_available = False

        while time.time() - wait_start < max_wait:
            try:
                # Check if result.pkl exists on remote
                stdin, stdout, stderr = self.ssh_client.exec_command(
                    f"test -f {base_dir}/result.pkl && echo exists || echo missing"
                )
                stdout.channel.recv_exit_status()  # Wait for command to complete
                output = stdout.read().decode("utf-8").strip()
                if output == "exists":
                    result_available = True
                    break
            except Exception as e:
                self.logger.debug(f"Error checking for result file: {e}")
            time.sleep(1)

        if not result_available:
            # Debug: list files on remote
            try:
                stdin, stdout, stderr = self.ssh_client.exec_command(
                    f"ls -la {base_dir}/"
                )
                stdout.channel.recv_exit_status()
                files = stdout.read().decode("utf-8")
                self.logger.error(
                    f"Result file not found. Remote directory contents:\n{files}"
                )
            except Exception:
                pass
            raise FileNotFoundError(f"Job did not complete within {max_wait}s timeout")

        # Download result
        self.logger.info("📥 Retrieving results...")
        result_path = os.path.join(self.launcher.project_path, "result.pkl")
        try:
            sftp.get(f"{base_dir}/result.pkl", result_path)
            self.logger.info("✅ Results retrieved successfully")
        except Exception as e:
            self.logger.error(f"Failed to download result file: {e}")
            raise

        # Load result BEFORE cleanup (cleanup removes result.pkl)
        with open(result_path, "rb") as f:
            result = dill.load(f)

        # Close tunnel now that job is complete
        if self.tunnel:
            self.tunnel.__exit__(None, None, None)
            self.tunnel = None

        # Clean up remote temporary files (preserve venv and cache)
        self.ssh_client.exec_command(
            f"cd {base_dir} && "
            f"find . -maxdepth 1 -type f \\( -name '*.py' -o -name '*.pkl' -o -name '*.sh' -o -name '*.txt' \\) "
            f"! -name 'requirements.txt' -delete && "
            f"rm -rf .slogs/server 2>/dev/null || true"
        )

        # Clean up local temporary files after successful download
        # Note: result.pkl is included in cleanup but we've already loaded it
        self._cleanup_local_temp_files()

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
        source_path = os.path.dirname(
            self.launcher.module_path
        )  # Parent of slurmray package

        # Walk through the slurmray directory
        for root, dirs, files in os.walk(os.path.join(source_path, "slurmray")):
            # Skip __pycache__
            if "__pycache__" in root:
                continue

            rel_path = os.path.relpath(root, source_path)
            remote_dir = os.path.join(base_dir, rel_path)

            # Create remote directory
            try:
                stdin, stdout, stderr = self.ssh_client.exec_command(
                    f"mkdir -p {remote_dir}"
                )
                stdout.channel.recv_exit_status()  # Wait for directory to be created
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

        text = text.replace(
            "{{PROJECT_PATH}}", f'"{base_dir}"'
        )  # On remote, we use absolute path

        # Desi is a single machine (or we treat it as such for now).
        # Ray should run in local mode or with address='auto' but without Slurm specifics.
        # It's basically local execution on a remote machine.
        # Use port 0 to let Ray choose a free port to avoid "address already in use" errors if previous run didn't clean up
        # However, we need to know the port for the tunnel.
        # Better strategy: Try to clean up previous ray instances before starting
        # Add Ray warning suppression to runtime_env if not already present
        runtime_env = self.launcher.runtime_env.copy()
        if "env_vars" not in runtime_env:
            runtime_env["env_vars"] = {}
        if "RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO" not in runtime_env["env_vars"]:
            runtime_env["env_vars"]["RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO"] = "0"

        local_mode = f"\n\tinclude_dashboard=True,\n\tdashboard_host='0.0.0.0',\n\tdashboard_port=8265,\nruntime_env = {runtime_env},\n"

        text = text.replace(
            "{{LOCAL_MODE}}",
            local_mode,
        )
        with open(os.path.join(self.launcher.project_path, "spython.py"), "w") as f:
            f.write(text)

    def _write_runner_script(self, filename, base_dir):
        """Write bash script to set up env and run wrapper"""
        # Determine Python command
        if self.pyenv_python_cmd:
            # Use pyenv: the command already includes eval and pyenv shell
            python_cmd = self.pyenv_python_cmd.split(" && ")[
                -1
            ]  # Extract just "python" from the command
            python3_cmd = python_cmd.replace("python", "python3")
            pyenv_setup = self.pyenv_python_cmd.rsplit(" && ", 1)[
                0
            ]  # Get "eval ... && pyenv shell X.Y.Z"
            use_pyenv = True
        else:
            # Fallback to system Python
            python_cmd = "python"
            python3_cmd = "python3"
            pyenv_setup = ""
            use_pyenv = False

        content = f"""#!/bin/bash
# Desi Runner Script
set -e  # Exit immediately if a command exits with a non-zero status

# Clean up any previous Ray instances (silently)
pkill -f ray 2>/dev/null || true

# Setup pyenv if available
"""

        if use_pyenv:
            content += f"""# Using pyenv for Python version management
export PATH="$HOME/.pyenv/bin:/usr/local/bin:/opt/pyenv/bin:$PATH"
{pyenv_setup}
"""
        else:
            content += """# pyenv not available, using system Python
"""

        content += f"""
# Check for force reinstall flag
if [ -f ".force_reinstall" ]; then
    echo "🔄 Force reinstall detected: removing existing virtualenv..."
    rm -rf venv
    rm -f .force_reinstall
fi

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
"""

        if use_pyenv:
            content += f"""    {pyenv_setup} && {python3_cmd} -m venv venv
"""
        else:
            content += f"""    {python3_cmd} -m venv venv
"""

        content += f"""else
    echo "✅ Using existing virtual environment"
fi

# Activate venv
source venv/bin/activate

# Install dependencies if requirements file exists
if [ -f requirements.txt ]; then
    echo "📥 Installing dependencies from requirements.txt..."
    if pip install --progress-bar off --quiet -r requirements.txt >/dev/null 2>&1; then
        echo "✅ Dependencies installed"
    else
        echo "❌ Error installing dependencies" >&2
        pip install --progress-bar off -r requirements.txt 2>&1 | grep -E "(error|Error|ERROR|failed|Failed|FAILED|WARNING)" >&2 || true
        exit 1
    fi
else
    echo "⚠️  No requirements.txt found, skipping dependency installation"
fi

# Add current directory to PYTHONPATH to make 'slurmray' importable
export PYTHONPATH=$PYTHONPATH:.

# Run wrapper (Smart Lock + Script execution)
echo "🔒 Acquiring Smart Lock and starting job..."
# Use venv Python (venv is already activated above)
"""

        # After venv activation, use the venv's python, not the system/pyenv python
        content += """python desi_wrapper.py
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
    lock_fd = open(LOCK_FILE, 'w')
    try:
        # Try to acquire non-blocking exclusive lock
        fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except IOError:
        lock_fd.close()
        return None

def main():
    lock_fd = None
    retries = 0
    
    print("🔒 Attempting to acquire Smart Lock...")
    while lock_fd is None:
        lock_fd = acquire_lock()
        if lock_fd is None:
            if retries == 0:
                print("⏳ Waiting for resources to become available (another job may be running)...")
            elif retries % 10 == 0:  # Log every 10 retries (every 5 minutes)
                print(f"⏳ Still waiting... (attempt {{retries}}/{{MAX_RETRIES}})")
            time.sleep(RETRY_DELAY)
            retries += 1
            if retries > MAX_RETRIES:
                print(f"❌ Timeout: Could not acquire lock after {{MAX_RETRIES}} attempts ({{MAX_RETRIES * RETRY_DELAY / 60:.1f}} minutes)")
                sys.exit(1)
    
    print("✅ Lock acquired! Starting job execution...")
    # Lock acquired, run payload
    # Use venv Python if available, otherwise fallback to sys.executable
    venv_python = os.path.join(os.path.dirname(__file__), "venv", "bin", "python")
    if os.path.exists(venv_python):
        python_cmd = venv_python
    else:
        python_cmd = sys.executable
    try:
        subprocess.check_call([python_cmd, "spython.py"])
    finally:
        # Release lock
        print("🔓 Releasing Smart Lock...")
        fcntl.lockf(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
        print("✅ Lock released")

if __name__ == "__main__":
    main()
"""
        with open(os.path.join(self.launcher.project_path, filename), "w") as f:
            f.write(content)
