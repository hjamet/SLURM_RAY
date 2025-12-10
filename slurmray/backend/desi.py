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

    def run(self, cancel_old_jobs: bool = True, wait: bool = True) -> Any:
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

        # Add slurmray (unpinned for now to match legacy behavior, but could be pinned)
        # Check if slurmray is already in requirements.txt to avoid duplicates
        req_file = f"{self.launcher.project_path}/requirements.txt"
        with open(req_file, "r") as f:
            content = f.read()
        if "slurmray" not in content.lower():
            with open(req_file, "a") as f:
                f.write("slurmray\n")

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
        
        # Fail-fast: ensure func_name.txt is present and will be uploaded
        func_name_txt = "func_name.txt"
        func_name_path = os.path.join(self.launcher.project_path, func_name_txt)
        if not os.path.exists(func_name_path):
            error_msg = f"❌ ERROR: func_name.txt not found locally at {func_name_path}. Cannot proceed without function name."
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        if func_name_txt not in files_to_push:
            files_to_push.append(func_name_txt)
        
        if files_to_push:
            self.logger.info(f"📤 Uploading {len(files_to_push)} file(s) to server...")
            for file in files_to_push:
                sftp.put(
                    os.path.join(self.launcher.project_path, file), f"{base_dir}/{file}"
                )
        
        # Verify func_name.txt was uploaded successfully (fail-fast)
        stdin, stdout, stderr = self.ssh_client.exec_command(
            f"test -f {base_dir}/{func_name_txt} && echo 'exists' || echo 'missing'"
        )
        stdout.channel.recv_exit_status()
        if "missing" in stdout.read().decode("utf-8").strip():
            error_msg = f"❌ ERROR: func_name.txt upload failed. File not found on server at {base_dir}/{func_name_txt}"
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg)

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

        # Filter valid files
        valid_files = []
        for file in self.launcher.files:
            # Skip invalid paths
            if (
                not file
                or file == "."
                or file == ".."
                or file.startswith("./")
                or file.startswith("../")
            ):
                self.logger.warning(f"Skipping invalid file path: {file}")
                continue
            valid_files.append(file)

        # Use incremental sync for local files
        if valid_files:
            self._sync_local_files_incremental(sftp, base_dir, valid_files)

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
        
        # Determine command based on wait mode
        if wait:
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
                
                time.sleep(5)

            if not result_available:
                self.logger.error("❌ Timeout waiting for result file.")
                raise TimeoutError("Timeout waiting for result file on Desi.")

            # Download result
            self.logger.info("📥 Downloading result...")
            local_result_path = os.path.join(self.launcher.project_path, "result.pkl")
            sftp.get(f"{base_dir}/result.pkl", local_result_path)

            # Load result
            with open(local_result_path, "rb") as f:
                result = dill.load(f)

            self.logger.info("✅ Result received!")

            # Close tunnel now that job is complete
            if self.tunnel:
                self.tunnel.__exit__(None, None, None)
                self.tunnel = None

        else:
             # Async mode: Run with nohup and redirect to log file
             log_file = "desi.log"
             cmd = f"cd {base_dir} && nohup ./run_desi.sh > {log_file} 2>&1 & echo $!"
             stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
             pid = stdout.read().decode("utf-8").strip()
             self.logger.info(f"Async mode: Job started with PID {pid}. Log file: {base_dir}/{log_file}")
             
             return pid

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

    def cancel(self, job_id: str):
        """Cancel job on Desi"""
        self.logger.info(f"Canceling Desi job {job_id}...")
        self._connect()
        try:
             # Try to kill the process and process group
             # job_id is PID from nohup
             # Use negative PID to kill process group
             self.ssh_client.exec_command(f"kill -TERM -{job_id}")
             self.logger.info(f"Sent kill signal to process group {job_id}")
             
             # Also kill the specific PID just in case
             self.ssh_client.exec_command(f"kill -9 {job_id}")
        except Exception as e:
             self.logger.warning(f"Failed to cancel Desi job: {e}")

    def get_result(self, job_id: str) -> Any:
        """Get result for Desi execution"""
        self._connect()
        base_dir = f"/home/{self.launcher.server_username}/slurmray_desi/{self.launcher.project_name}"
        local_path = os.path.join(self.launcher.project_path, "result.pkl")
        
        try:
            sftp = self.ssh_client.open_sftp()
            sftp.stat(f"{base_dir}/result.pkl")
            sftp.get(f"{base_dir}/result.pkl", local_path)
            with open(local_path, "rb") as f:
                return dill.load(f)
        except Exception:
            return None

    def get_logs(self, job_id: str) -> Any:
        """Get logs for Desi execution"""
        self._connect()
        base_dir = f"/home/{self.launcher.server_username}/slurmray_desi/{self.launcher.project_name}"
        log_file = "desi.log" # Assumed from async execution
        remote_log = f"{base_dir}/{log_file}"
        
        try:
             stdin, stdout, stderr = self.ssh_client.exec_command(f"cat {remote_log}")
             for line in stdout:
                 yield line
        except Exception as e:
             yield f"Error reading remote log: {e}"

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
    VENV_EXISTED=true
fi

# Activate venv
source venv/bin/activate

# Install dependencies if requirements file exists and is not empty
if [ -f requirements.txt ]; then
    # Check if requirements.txt is empty (only whitespace)
    if [ -s requirements.txt ]; then
        echo "📥 Installing dependencies from requirements.txt..."
        
        # Get installed packages once (fast, single command) - create lookup file
        uv pip list --format=freeze 2>/dev/null | sed 's/==/ /' | awk '{{print $1" "$2}}' > /tmp/installed_packages.txt || touch /tmp/installed_packages.txt
        
        # Process requirements: filter duplicates and check what needs installation
        INSTALL_ERRORS=0
        SKIPPED_COUNT=0
        > /tmp/to_install.txt  # Clear file
        
        while IFS= read -r line || [ -n "$line" ]; do
            # Skip empty lines and comments
            line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
            if [ -z "$line" ] || [ "${{line#"#"}}" != "$line" ]; then
                continue
            fi
            
            # Extract package name (remove version specifiers and extras)
            pkg_name=$(echo "$line" | sed 's/[<>=!].*//' | sed 's/\\[.*\\]//' | sed 's/[[:space:]]*//' | tr '[:upper:]' '[:lower:]')
            if [ -z "$pkg_name" ]; then
                continue
            fi
            
            # Skip duplicates (check if we've already processed this package)
            if grep -qi "^$pkg_name$" /tmp/seen_packages.txt 2>/dev/null; then
                continue
            fi
            echo "$pkg_name" >> /tmp/seen_packages.txt
            
            # Extract required version if present
            required_version=""
            if echo "$line" | grep -q "=="; then
                required_version=$(echo "$line" | sed 's/.*==\\([^;]*\\).*/\\1/' | sed 's/[[:space:]]*//')
            fi
            
            # Check if package is already installed with correct version
            installed_version=$(grep -i "^$pkg_name " /tmp/installed_packages.txt 2>/dev/null | awk '{{print $2}}' | head -1)
            
            if [ -n "$installed_version" ]; then
                if [ -z "$required_version" ] || [ "$installed_version" = "$required_version" ]; then
                    echo "  ⏭️  $pkg_name==$installed_version (already installed)"
                    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
                    continue
                fi
            fi
            
            # Package not installed or version mismatch, add to install list
            echo "$line" >> /tmp/to_install.txt
        done < requirements.txt
        
        # Install packages that need installation
        if [ -s /tmp/to_install.txt ]; then
            > /tmp/install_errors.txt  # Track errors
            while IFS= read -r line; do
                pkg_name=$(echo "$line" | sed 's/[<>=!].*//' | sed 's/\\[.*\\]//' | sed 's/[[:space:]]*//')
                if uv pip install --quiet "$line" >/dev/null 2>&1; then
                    echo "  ✅ $pkg_name"
                else
                    echo "  ❌ $pkg_name"
                    echo "1" >> /tmp/install_errors.txt
                    # Show error details
                    uv pip install "$line" 2>&1 | grep -E "(error|Error|ERROR|failed|Failed|FAILED)" | head -3 | sed 's/^/      /' || true
                fi
            done < /tmp/to_install.txt
            INSTALL_ERRORS=$(wc -l < /tmp/install_errors.txt 2>/dev/null | tr -d ' ' || echo "0")
            rm -f /tmp/install_errors.txt
        fi
        
        # Count newly installed packages before cleanup
        NEWLY_INSTALLED=0
        if [ -s /tmp/to_install.txt ]; then
            NEWLY_INSTALLED=$(wc -l < /tmp/to_install.txt 2>/dev/null | tr -d ' ' || echo "0")
        fi
        
        # Cleanup temp files
        rm -f /tmp/installed_packages.txt /tmp/seen_packages.txt /tmp/to_install.txt
        
        if [ $INSTALL_ERRORS -eq 0 ]; then
            if [ $SKIPPED_COUNT -gt 0 ]; then
                echo "✅ All dependencies up to date ($SKIPPED_COUNT already installed, $NEWLY_INSTALLED newly installed)"
            else
                echo "✅ All dependencies installed successfully"
            fi
        else
            echo "❌ Failed to install $INSTALL_ERRORS package(s)" >&2
            exit 1
        fi
    else
        if [ "$VENV_EXISTED" = "true" ]; then
            echo "✅ All dependencies already installed (requirements.txt is empty)"
        else
            echo "⚠️  requirements.txt is empty, skipping dependency installation"
        fi
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
        """Write python wrapper for Smart Lock with queue management"""
        content = f"""
import os
import sys
import time
import fcntl
import subprocess
import json

LOCK_FILE = "/tmp/slurmray_desi.lock"
QUEUE_FILE = "/tmp/slurmray_desi.queue"
MAX_RETRIES = 1000
RETRY_DELAY = 30 # seconds

def read_queue():
    '''Read queue file (read-only, no lock needed)'''
    if not os.path.exists(QUEUE_FILE):
        return []
    try:
        with open(QUEUE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def write_queue(queue_data):
    '''Write queue file with exclusive lock'''
    max_retries = 10
    retry_delay = 0.1
    for attempt in range(max_retries):
        try:
            queue_fd = open(QUEUE_FILE, 'w')
            try:
                fcntl.lockf(queue_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                json.dump(queue_data, queue_fd, indent=2)
                queue_fd.flush()
                os.fsync(queue_fd.fileno())
                fcntl.lockf(queue_fd, fcntl.LOCK_UN)
                queue_fd.close()
                return True
            except IOError:
                queue_fd.close()
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return False
        except IOError:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return False
    return False

def add_to_queue(pid, user, func_name, project_dir, status):
    '''Add or update entry in queue'''
    queue = read_queue()
    # Remove existing entry with same PID if present
    queue = [entry for entry in queue if entry.get("pid") != str(pid)]
    # Add new entry
    entry = {{
        "pid": str(pid),
        "user": user,
        "func_name": func_name,
        "status": status,
        "timestamp": int(time.time()),
        "project_dir": project_dir
    }}
    queue.append(entry)
    write_queue(queue)

def remove_from_queue(pid):
    '''Remove entry from queue'''
    queue = read_queue()
    queue = [entry for entry in queue if entry.get("pid") != str(pid)]
    write_queue(queue)

def update_queue_status(pid, status):
    '''Update status of an entry in queue'''
    queue = read_queue()
    for entry in queue:
        if entry.get("pid") == str(pid):
            entry["status"] = status
            write_queue(queue)
            return True
    return False

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
    pid = os.getpid()
    user = os.getenv('USER', 'unknown')
    project_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Read function name from func_name.txt (fail-fast if missing or empty)
    func_name_path = os.path.join(project_dir, "func_name.txt")
    if not os.path.exists(func_name_path):
        print("❌ ERROR: func_name.txt not found at " + func_name_path)
        sys.exit(1)
    
    try:
        with open(func_name_path, 'r') as f:
            func_name = f.read().strip()
    except IOError as e:
        print("❌ ERROR: Failed to read func_name.txt: " + str(e))
        sys.exit(1)
    
    if not func_name:
        print("❌ ERROR: func_name.txt is empty at " + func_name_path)
        sys.exit(1)
    
    # Add to queue as waiting at startup
    add_to_queue(pid, user, func_name, project_dir, "waiting")
    
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
                # Remove from queue before exiting
                remove_from_queue(pid)
                sys.exit(1)
    
    # Update queue status to running and write function name to lock file
    update_queue_status(pid, "running")
    lock_fd.seek(0)
    lock_fd.truncate()
    lock_fd.write(str(pid) + "\\n" + user + "\\n" + func_name + "\\n" + project_dir + "\\n")
    lock_fd.flush()
    
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
        # Remove from queue before releasing lock
        remove_from_queue(pid)
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
