import os
import sys
import time
import re
import paramiko
import subprocess
import dill
import random
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
        self._log_cursors = {}  # Store cursor position for each job_id

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

        sftp = self.get_sftp()

        # Base directory on server (organized by project name)
        base_dir = f"/home/{self.launcher.server_username}/slurmray-server/{self.launcher.project_name}"

        # --- LOCK MECHANISM START ---
        # Acquire lock to prevent race conditions during sync
        lock_dir = f"/home/{self.launcher.server_username}/slurmray-server/.{self.launcher.project_name}.lock"
        self.logger.info("Acquiring sync lock...")
        lock_acquired = False
        start_lock_time = time.time()
        timeout = 600 # 10 minutes timeout
        
        while not lock_acquired:
            try:
                # mkdir is atomic on POSIX
                self.ssh_client.exec_command(f"mkdir -p /home/{self.launcher.server_username}/slurmray-server") # Ensure parent exists
                stdin, stdout, stderr = self.ssh_client.exec_command(f"mkdir {lock_dir}")
                exit_status = stdout.channel.recv_exit_status()
                if exit_status == 0:
                    lock_acquired = True
                else:
                    # Check timeout
                    if time.time() - start_lock_time > timeout:
                        self.logger.warning("Timeout waiting for lock. Breaking lock (dangerous if another process is active).")
                        self.ssh_client.exec_command(f"rm -rf {lock_dir}")
                    time.sleep(2)
            except Exception as e:
                self.logger.warning(f"Error acquiring lock: {e}")
                time.sleep(2)
        
        self.logger.info("Sync lock acquired.")

        try:
            # Generate requirements first to check venv hash
            self._generate_requirements()

            # Add slurmray (unpinned for now to match legacy behavior, but could be pinned)
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
                self.logger.info("Force reinstall enabled: removing existing virtualenv...")
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

            # --- FORCE REINSTALL PROJECT LOGIC ---
            if self.launcher.force_reinstall_project:
                self.logger.warning(f"Force reinstall project enabled: cleaning {base_dir} (preserving venv if possible)...")
                cmd = f"find {base_dir} -mindepth 1 -maxdepth 1 ! -name 'venv' -exec rm -rf {{}} +"
                self.ssh_client.exec_command(cmd)
                self.ssh_client.exec_command(f"rm -f {base_dir}/.slogs/.remote_file_hashes.json")

            # Smart cleanup: preserve venv if hash matches
            self.ssh_client.exec_command(f"mkdir -p {base_dir}/.slogs/server")
            if should_recreate_venv:
                 # Clean server logs only (venv will be recreated by script if needed)
                self.ssh_client.exec_command(f"rm -rf {base_dir}/.slogs/server/*")
                if self.launcher.force_reinstall_venv:
                    self.ssh_client.exec_command(f"touch {base_dir}/.force_reinstall")
            else:
                 # Clean server logs only, preserve venv
                 # Unlike previous Desi logic which cleaned everything, we now match Slurm logic: prevent deletion of project files.
                self.ssh_client.exec_command(f"rm -rf {base_dir}/.slogs/server/*")
                self.ssh_client.exec_command(f"rm -f {base_dir}/.force_reinstall")

            # Generate Python script (spython.py) that will run on Desi
            self._write_python_script(base_dir)

            # Optimize requirements
            venv_cmd = (
                f"source {base_dir}/venv/bin/activate &&"
                if not should_recreate_venv
                else ""
            )
            req_file_to_push = self._optimize_requirements(self.ssh_client, venv_cmd)

            # Prepare files to push
            # Include generated files in list
            files_to_sync = self.launcher.files.copy()
            
            # generated files handling
            # generated files handling - STRICT WHITELIST to avoid uploading result.pkl or other garbage
            # We explicitly list the files we expect to generate and upload as payload.
            # All other files (source code, data) should be handled by the user via 'files=[...]'
            whitelist_files = [
                "func.pkl",
                "args.pkl",
                "spython.py",
                "func_source.py",  # If source extraction used
                "func_name.txt",
                "serialization_method.txt",
                # "requirements_to_install.txt" is handled separately below (optimized_reqs)
            ]
            
            generated_files = []
            for fname in whitelist_files:
                fpath = os.path.join(self.launcher.project_path, fname)
                if os.path.exists(fpath):
                    generated_files.append(fname)

            # Fail-fast: check func_name.txt
            func_name_txt = "func_name.txt"
            func_name_path = os.path.join(self.launcher.project_path, func_name_txt)
            if not os.path.exists(func_name_path):
                error_msg = f"❌ ERROR: func_name.txt not found locally at {func_name_path}."
                self.logger.error(error_msg)
                raise FileNotFoundError(error_msg)
            
            # Add generated files to sync list doesn't work easily because they are in project_path, not pwd_path
            # We will push them manually as before for now, BUT INSIDE THE LOCK.

            # Filter valid files from launcher.files
            valid_files = []
            for file in self.launcher.files:
                 if (not file or file == "." or file == ".." or file.startswith("./") or file.startswith("../")):
                      continue
                 valid_files.append(file)

            # Sync local files (incremental)
            if valid_files:
                self._sync_local_files_incremental(sftp, base_dir, valid_files)

            # Push generated/critical files (always overwrite)
            if generated_files:
                self.logger.info(f"📤 Uploading {len(generated_files)} generated file(s) to server...")
                
                # Define progress callback
                def progress_callback(transferred, total):
                    # Log every 10MB or 100%
                    if total > 0:
                        percent = int((transferred / total) * 100)
                        # Avoid spamming logs - only log huge files progress or completion? 
                        # Actually standard logger might be too verbose if we log every chunk.
                        # Let's log only every 10MB
                        if transferred % (10 * 1024 * 1024) < 32768: # Rough check
                             self.logger.info(f"    ... transferred {transferred/1024/1024:.1f} MB ({percent}%)")

                for file in generated_files:
                    local_path = os.path.join(self.launcher.project_path, file)
                    remote_path = f"{base_dir}/{file}"
                    file_size = os.path.getsize(local_path)
                    
                    if file_size > 50 * 1024 * 1024: # 50 MB
                        self.logger.warning(f"⚠️  Large generated file detected: {file} ({file_size/1024/1024:.1f} MB). This might take a while.")
                    
                    sftp.put(local_path, remote_path, callback=None if file_size < 10*1024*1024 else progress_callback)

            # Verify func_name.txt uploaded
            stdin, stdout, stderr = self.ssh_client.exec_command(
                f"test -f {base_dir}/{func_name_txt} && echo 'exists' || echo 'missing'"
            )
            stdout.channel.recv_exit_status()
            if "missing" in stdout.read().decode("utf-8").strip():
                raise FileNotFoundError(f"func_name.txt upload failed.")

            # Push requirements
            if os.path.exists(req_file_to_push):
                sftp.put(req_file_to_push, f"{base_dir}/requirements.txt")
            else:
                 try: sftp.remove(f"{base_dir}/requirements.txt")
                 except IOError: pass

            # Store venv hash
            if os.path.exists(req_file):
                with open(req_file, "r") as f:
                    req_lines = f.readlines()
                current_hash = dep_manager.compute_requirements_hash(req_lines)
                self.ssh_client.exec_command(f"mkdir -p {base_dir}/.slogs")
                self.ssh_client.exec_command(f"echo '{current_hash}' > {base_dir}/.slogs/venv_hash.txt")
                dep_manager.store_venv_hash(current_hash)

            # Update retention
            self._update_retention_timestamp(
                self.ssh_client, base_dir, self.launcher.retention_days
            )

            # Create runner script
            runner_script = "run_desi.sh"
            self._write_runner_script(runner_script, base_dir)
            sftp.put(
                os.path.join(self.launcher.project_path, runner_script),
                f"{base_dir}/{runner_script}",
            )
            self.ssh_client.exec_command(f"chmod +x {base_dir}/{runner_script}")

            # Desi Wrapper
            desi_wrapper_script = "desi_wrapper.py"
            self._write_desi_wrapper(desi_wrapper_script)
            sftp.put(
                os.path.join(self.launcher.project_path, desi_wrapper_script),
                f"{base_dir}/{desi_wrapper_script}",
            )
        
        finally:
            # RELEASE LOCK
            try:
                self.ssh_client.exec_command(f"rm -rf {lock_dir}")
                self.logger.info("Sync lock released.")
            except Exception as e:
                self.logger.warning(f"Failed to release lock: {e}")

        # Run the script
        self.logger.info("🚀 Starting job execution...")
        
        # Determine command based on wait mode
        if wait:
            cmd = f"cd {base_dir} && ./run_desi.sh"
            stdin, stdout, stderr = self.ssh_client.exec_command(cmd, get_pty=True)
            
            # Stream output
            ray_started = False
            dashboard_url = None

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
                        else:
                             self.logger.warning(f"⚠️ Could not parse dashboard URL from line: {line_stripped}")

                    # Start SSH Tunnel
                    if not self.tunnel and dashboard_url:
                        try:
                            # Parse port cleanly
                            try:
                                remote_port = int(dashboard_url.split(":")[-1].strip("/"))
                                self.logger.debug(f"🔍 Parsed remote dashboard port: {remote_port}")
                            except ValueError:
                                self.logger.warning(f"⚠️ Could not parse port from {dashboard_url}. Defaulting to 8265.")
                                remote_port = 8265

                            self.tunnel = SSHTunnel(
                                ssh_host=self.launcher.server_ssh,
                                ssh_username=self.launcher.server_username,
                                ssh_password=self.launcher.server_password,
                                remote_host="127.0.0.1",
                                local_port=0, # Dynamic port to avoid contention
                                remote_port=remote_port,
                                logger=self.logger,
                            )
                            self.tunnel.__enter__()
                            self.logger.info(
                                f"🌐 Dashboard accessible locally at http://localhost:{self.tunnel.local_port}"
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

            return result

        else:
             # Async mode: Run with nohup and redirect to log file
             log_file = "desi.log"
             cmd = f"cd {base_dir} && nohup ./run_desi.sh > {log_file} 2>&1 < /dev/null & echo $!"
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
        base_dir = f"/home/{self.launcher.server_username}/slurmray-server/{self.launcher.project_name}"
        local_path = os.path.join(self.launcher.project_path, "result.pkl")
        
        try:
            sftp = self.get_sftp()
            sftp.stat(f"{base_dir}/result.pkl")
            sftp.get(f"{base_dir}/result.pkl", local_path)
            with open(local_path, "rb") as f:
                return dill.load(f)
        except Exception:
            return None

    def get_logs(self, job_id: str) -> Any:
        """Get logs for Desi execution"""
        self._connect()
        base_dir = f"/home/{self.launcher.server_username}/slurmray-server/{self.launcher.project_name}"
        log_file = "desi.log" # Assumed from async execution
        remote_log = f"{base_dir}/{log_file}"
        # print(f"DEBUG: Trying to access log at {remote_log}")
        
        try:
            sftp = self.get_sftp()
            
            # Use seek if we have a cursor
            cursor = self._log_cursors.get(job_id, 0)
            
            try:
                with sftp.file(remote_log, 'r') as f:
                    # Move to last position
                    f.seek(cursor)
                    
                    # Read new content
                    new_content = f.read()
                    
                    if new_content:
                        # Update cursor
                        self._log_cursors[job_id] = f.tell()
                        
                        # Yield lines
                        if isinstance(new_content, bytes):
                            new_content = new_content.decode('utf-8')
                            
                        # Split by lines, but careful with partial lines?
                        # For simplicity, we just yield the chunk or split lines.
                        # RayLauncher expects lines.
                        for line in new_content.splitlines(keepends=True):
                            yield line
            except FileNotFoundError:
                 yield "Log file not found (yet)."
            except IOError:
                 pass
                 
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

        # Pre-import logic for dill compatibility AND Dynamic Port Selection
        # We inject code to find a free port on the remote machine for the dashboard
        pre_import = "import socket\nimport random\n"
        pre_import += "try:\n"
        pre_import += "    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:\n"
        pre_import += "        s.bind(('', 0))\n"
        pre_import += "        _dynamic_dashboard_port = s.getsockname()[1]\n"
        pre_import += "    print(f'🔧 Dynamic Dashboard Port: {_dynamic_dashboard_port}')\n"
        pre_import += "except Exception as e:\n"
        pre_import += "    print(f'⚠️ Failed to find dynamic port: {e}')\n"
        pre_import += "    _dynamic_dashboard_port = 8265\n\n"

        if hasattr(self.launcher, "func") and self.launcher.func:
            func_module = self.launcher.func.__module__
            self.logger.info(f"DEBUG: Detected func_module: {func_module}")
            if func_module and func_module != "__main__":
                root_pkg = func_module.split(".")[0]
                self.logger.info(f"DEBUG: injecting pre-import for {root_pkg}")
                pre_import += f"try:\n    import {root_pkg}\n    print(f'Imported {root_pkg} for dill compatibility')\nexcept ImportError as e:\n    print(f'Pre-import of {root_pkg} failed: {{e}}')\n"
        
        text = text.replace("{{PRE_IMPORT}}", pre_import)

        # Use user-specific temp directory by default if not set
        user_temp_dir = f"/tmp/ray_{self.launcher.server_username}"
        
        # We use the variable _dynamic_dashboard_port which is defined in the injected code above
        local_mode = f"\n\tinclude_dashboard=True,\n\tdashboard_host='0.0.0.0',\n\tdashboard_port=_dynamic_dashboard_port,\n\t_temp_dir='{user_temp_dir}',\nruntime_env = {runtime_env},\n"

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
# pkill -f ray 2>/dev/null || true
# disabled to allow concurrency

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
        
        # Create temp files safely
        TMP_INSTALLED=$(mktemp)
        TMP_SEEN=$(mktemp)
        TMP_TO_INSTALL=$(mktemp)
        TMP_ERRORS=$(mktemp)
        
        # Get installed packages once (fast, single command) - create lookup file
        uv pip list --format=freeze 2>/dev/null | sed 's/==/ /' | awk '{{print $1" "$2}}' > "$TMP_INSTALLED" || touch "$TMP_INSTALLED"
        
        # Process requirements: filter duplicates and check what needs installation
        INSTALL_ERRORS=0
        SKIPPED_COUNT=0
        > "$TMP_TO_INSTALL"  # Clear file
        
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
            if grep -qi "^$pkg_name$" "$TMP_SEEN" 2>/dev/null; then
                continue
            fi
            echo "$pkg_name" >> "$TMP_SEEN"
            
            # Extract required version if present
            required_version=""
            if echo "$line" | grep -q "=="; then
                required_version=$(echo "$line" | sed 's/.*==\\([^;]*\\).*/\\1/' | sed 's/[[:space:]]*//')
            fi
            
            # Check if package is already installed with correct version
            installed_version=$(grep -i "^$pkg_name " "$TMP_INSTALLED" 2>/dev/null | awk '{{print $2}}' | head -1)
            
            if [ -n "$installed_version" ]; then
                if [ -z "$required_version" ] || [ "$installed_version" = "$required_version" ]; then
                    echo "  ⏭️  $pkg_name==$installed_version (already installed)"
                    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
                    continue
                fi
            fi
            
            # Package not installed or version mismatch, add to install list
            echo "$line" >> "$TMP_TO_INSTALL"
        done < requirements.txt
        
        # Install packages that need installation
        if [ -s "$TMP_TO_INSTALL" ]; then
            > "$TMP_ERRORS"  # Track errors
            while IFS= read -r line; do
                pkg_name=$(echo "$line" | sed 's/[<>=!].*//' | sed 's/\\[.*\\]//' | sed 's/[[:space:]]*//')
                if uv pip install --quiet "$line" >/dev/null 2>&1; then
                    echo "  ✅ $pkg_name"
                else
                    echo "  ❌ $pkg_name"
                    echo "1" >> "$TMP_ERRORS"
                    # Show error details
                    uv pip install "$line" 2>&1 | grep -E "(error|Error|ERROR|failed|Failed|FAILED)" | head -3 | sed 's/^/      /' || true
                fi
            done < "$TMP_TO_INSTALL"
            INSTALL_ERRORS=$(wc -l < "$TMP_ERRORS" 2>/dev/null | tr -d ' ' || echo "0")
            rm -f "$TMP_ERRORS"
        fi
        
        # Count newly installed packages before cleanup
        NEWLY_INSTALLED=0
        if [ -s "$TMP_TO_INSTALL" ]; then
            NEWLY_INSTALLED=$(wc -l < "$TMP_TO_INSTALL" 2>/dev/null | tr -d ' ' || echo "0")
        fi
        
        # Cleanup temp files
        rm -f "$TMP_INSTALLED" "$TMP_SEEN" "$TMP_TO_INSTALL"
        
        if [ $INSTALL_ERRORS -eq 0 ]; then
            if [ $SKIPPED_COUNT -gt 0 ]; then
                echo "✅ All dependencies up to date ($SKIPPED_COUNT already installed, $NEWLY_INSTALLED newly installed)"
            else
                echo "✅ All dependencies installed successfully"
            fi
        else
            echo "❌ Failed to install $INSTALL_ERRORS package(s)" >&2
            echo "⚠️  Continuing execution despite installation errors..."
            # exit 1  <-- Disabled to allow flexible execution
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
        """Write python wrapper for Smart Lock with Resource Management"""
        
        # Load template
        template_path = os.path.join(self.launcher.module_path, "assets", "desi_wrapper_template.py")
        with open(template_path, "r") as f:
            content = f.read()
            
        # Resource Limits (Hardcoded for Desi based on audit)
        limits_cpu = 24
        limits_ram = 120
        limits_gpu_ids = [0, 1]
        
        # Inject Values
        content = content.replace("{{LIMIT_CPU}}", str(limits_cpu))
        content = content.replace("{{LIMIT_RAM}}", str(limits_ram))
        content = content.replace("{{LIMIT_GPU_IDS}}", str(limits_gpu_ids))
        
        content = content.replace("{{REQ_CPU}}", str(self.launcher.num_cpus))
        content = content.replace("{{REQ_RAM}}", str(self.launcher.memory))
        content = content.replace("{{REQ_GPU}}", str(self.launcher.num_gpus))
        
        job_name = getattr(self.launcher, "func_name", "Unknown Function")
        # Try to find valid function name
        if job_name == "Unknown Function" and hasattr(self.launcher, "func"):
            try:
                job_name = self.launcher.func.__name__
            except Exception:
                pass
                
        content = content.replace("{{JOB_NAME}}", str(job_name))
        content = content.replace("{{USER_NAME}}", str(self.launcher.server_username))
        
        # We need the remote project dir. 
        # base_dir is calculated in run(), but we are in _write_desi_wrapper inside run().
        # Actually _write_desi_wrapper is called at line 232 of desi.py
        # It doesn't receive base_dir argument in the original code, but we can reconstruct it.
        base_dir = f"/home/{self.launcher.server_username}/slurmray-server/{self.launcher.project_name}"
        content = content.replace("{{PROJECT_DIR}}", str(base_dir))
        
        with open(os.path.join(self.launcher.project_path, filename), "w") as f:
            f.write(content)

