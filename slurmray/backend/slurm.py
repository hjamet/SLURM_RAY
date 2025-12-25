import os
import sys
import time
import subprocess
import paramiko
import dill
import re
from getpass import getpass
from typing import Any

from slurmray.backend.base import ClusterBackend
from slurmray.backend.remote import RemoteMixin
from slurmray.utils import SSHTunnel, DependencyManager


class SlurmBackend(RemoteMixin):
    """Backend for Slurm cluster execution (local or remote via SSH)"""

    def __init__(self, launcher):
        super().__init__(launcher)
        self.ssh_client = None
        self._sftp_client = None
        self.ssh_client = None
        self.job_id = None

    def run(self, cancel_old_jobs: bool = True, wait: bool = True) -> Any:
        """Run the job on Slurm (locally or remotely)"""

        # Generate the Python script (spython.py) - needed for both modes
        if not self.launcher.server_run:
            self._write_python_script()
            self.script_file, self.job_name = self._write_slurm_script()
        else:
            # For server run, spython.py is generated inside __write_server_script -> slurmray_server.sh execution context?
            # Wait, in original code:
            # if not self.server_run:
            #    self.__write_python_script()
            #    self.script_file, self.job_name = self.__write_slurm_script()
            #
            # But in __launch_server, it writes server script, pushes files, and runs it.
            # The server script (slurmray_server.py) will instantiate RayLauncher on the cluster!
            # So when running on cluster (via SSH), RayLauncher is instantiated again on the remote machine.
            # On the remote machine, self.cluster will be True (detected /usr/bin/sbatch).
            # So the remote instance will enter the "if self.cluster:" block.
            pass

        if self.launcher.cluster:
            self.logger.info("Cluster detected, running on cluster...")
            # Cancel the old jobs
            if cancel_old_jobs:
                self.logger.info("Canceling old jobs...")
                subprocess.Popen(
                    ["scancel", "-u", os.environ["USER"]],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            # Launch the job
            # We need to ensure scripts are written if we are on the cluster
            if not hasattr(self, "script_file"):
                self._write_python_script()
                self.script_file, self.job_name = self._write_slurm_script()

            self._launch_job(self.script_file, self.job_name)
            
            if not wait:
                return self.job_id

        elif self.launcher.server_run:
            return self._launch_server(cancel_old_jobs, wait=wait)

        # Load the result
        # Note: In server_run mode, _launch_server downloads result.pkl
        # In cluster mode, we wait for result.pkl

        if self.launcher.cluster:
            # Wait for result in cluster mode (same filesystem)
            while not os.path.exists(
                os.path.join(self.launcher.project_path, "result.pkl")
            ):
                time.sleep(0.25)

        # Result should be there now
        with open(os.path.join(self.launcher.project_path, "result.pkl"), "rb") as f:
            result = dill.load(f)

        return result

    def cancel(self, job_id: str):
        """Cancel a job"""
        if self.launcher.cluster:
            self.logger.info(f"Canceling local job {job_id}...")
            try:
                subprocess.run(
                    ["scancel", job_id],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.logger.info(f"Job {job_id} canceled.")
            except Exception as e:
                self.logger.error(f"Failed to cancel job {job_id}: {e}")
        elif self.launcher.server_run and self.ssh_client:
            self.logger.info(f"Canceling remote job {job_id} via SSH...")
            try:
                # Check if connection is still active
                if (
                    self.ssh_client.get_transport()
                    and self.ssh_client.get_transport().is_active()
                ):
                    self.ssh_client.exec_command(f"scancel {job_id}")
                    self.logger.info(f"Remote job {job_id} canceled.")
                else:
                    self.logger.warning(
                        "SSH connection lost, cannot cancel remote job."
                    )
            except Exception as e:
                self.logger.error(f"Failed to cancel remote job {job_id}: {e}")
            finally:
                try:
                    self.ssh_client.close()
                except Exception:
                    pass

    # =========================================================================
    # Private methods extracted from RayLauncher
    # =========================================================================

    def _write_python_script(self):
        """Write the python script that will be executed by the job"""
        self.logger.info("Writing python script...")

        # Remove the old python script
        for file in os.listdir(self.launcher.project_path):
            if file.endswith(".py"):
                os.remove(os.path.join(self.launcher.project_path, file))

        # Write the python script
        with open(
            os.path.join(self.launcher.module_path, "assets", "spython_template.py"),
            "r",
        ) as f:
            text = f.read()

        text = text.replace("{{PROJECT_PATH}}", f'"{self.launcher.project_path}"')
        local_mode = ""
        if self.launcher.cluster or self.launcher.server_run:
            # Add Ray warning suppression to runtime_env if not already present
            runtime_env = self.launcher.runtime_env.copy()
            if "env_vars" not in runtime_env:
                runtime_env["env_vars"] = {}
            if "RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO" not in runtime_env["env_vars"]:
                runtime_env["env_vars"]["RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO"] = "0"

            local_mode = f"\n\taddress='auto',\n\tinclude_dashboard=True,\n\tdashboard_host='0.0.0.0',\n\tdashboard_port=8265,\nruntime_env = {runtime_env},\n"
        text = text.replace(
            "{{LOCAL_MODE}}",
            local_mode,
        )
        with open(os.path.join(self.launcher.project_path, "spython.py"), "w") as f:
            f.write(text)

    def _write_slurm_script(self):
        """Write the slurm script that will be executed by the job"""
        self.logger.info("Writing slurm script...")
        template_file = os.path.join(
            self.launcher.module_path, "assets", "sbatch_template.sh"
        )

        JOB_NAME = "{{JOB_NAME}}"
        NUM_NODES = "{{NUM_NODES}}"
        MEMORY = "{{MEMORY}}"
        RUNNING_TIME = "{{RUNNING_TIME}}"
        PARTITION_NAME = "{{PARTITION_NAME}}"
        COMMAND_PLACEHOLDER = "{{COMMAND_PLACEHOLDER}}"
        GIVEN_NODE = "{{GIVEN_NODE}}"
        COMMAND_SUFFIX = "{{COMMAND_SUFFIX}}"
        LOAD_ENV = "{{LOAD_ENV}}"
        PARTITION_SPECIFICS = "{{PARTITION_SPECIFICS}}"

        job_name = "{}_{}".format(
            self.launcher.project_name, time.strftime("%d%m-%Hh%M", time.localtime())
        )

        # Convert the time to xx:xx:xx format
        max_time = "{}:{}:{}".format(
            str(self.launcher.max_running_time // 60).zfill(2),
            str(self.launcher.max_running_time % 60).zfill(2),
            str(0).zfill(2),
        )

        # ===== Modified the template script =====
        with open(template_file, "r") as f:
            text = f.read()
        text = text.replace(
            JOB_NAME, os.path.join(self.launcher.project_path, job_name)
        )
        text = text.replace(NUM_NODES, str(self.launcher.node_nbr))
        text = text.replace(MEMORY, str(self.launcher.memory))
        text = text.replace(RUNNING_TIME, str(max_time))
        text = text.replace(
            PARTITION_NAME, str("gpu" if self.launcher.use_gpu > 0 else "cpu")
        )
        text = text.replace(
            COMMAND_PLACEHOLDER,
            str(f"{sys.executable} {self.launcher.project_path}/spython.py"),
        )
        text = text.replace(
            LOAD_ENV, str(f"module load {' '.join(self.launcher.modules)}")
        )
        text = text.replace(GIVEN_NODE, "")
        text = text.replace(COMMAND_SUFFIX, "")
        text = text.replace(
            "# THIS FILE IS A TEMPLATE AND IT SHOULD NOT BE DEPLOYED TO " "PRODUCTION!",
            "# THIS FILE IS MODIFIED AUTOMATICALLY FROM TEMPLATE AND SHOULD BE "
            "RUNNABLE!",
        )

        # ===== Add partition specifics =====
        if self.launcher.use_gpu > 0:
            text = text.replace(
                PARTITION_SPECIFICS,
                str("#SBATCH --gres gpu:1\n#SBATCH --gres-flags enforce-binding"),
            )
        else:
            text = text.replace(PARTITION_SPECIFICS, "#SBATCH --exclusive")

        # ===== Save the script =====
        script_file = "sbatch.sh"
        with open(os.path.join(self.launcher.project_path, script_file), "w") as f:
            f.write(text)

        return script_file, job_name

    def _launch_job(self, script_file: str = None, job_name: str = None):
        """Launch the job"""
        # ===== Submit the job =====
        self.logger.info("Start to submit job!")
        result = subprocess.run(
            ["sbatch", os.path.join(self.launcher.project_path, script_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.logger.error(f"Error submitting job: {result.stderr}")
            return

        # Extract job ID from output (format: "Submitted batch job 12345")
        job_id = None
        if result.stdout:
            match = re.search(r"Submitted batch job (\d+)", result.stdout)
            if match:
                job_id = match.group(1)

        if job_id:
            self.job_id = job_id
            self.logger.info(f"Job submitted with ID: {job_id}")
        else:
            self.logger.warning("Could not extract job ID from sbatch output")

        self.logger.info(
            "Job submitted! Script file is at: <{}>. Log file is at: <{}>".format(
                os.path.join(self.launcher.project_path, script_file),
                os.path.join(self.launcher.project_path, "{}.log".format(job_name)),
            )
        )

        # Wait for log file to be created and job to start running
        self._monitor_queue(job_name, job_id)

    def _monitor_queue(self, job_name, job_id):
        current_queue = None
        queue_log_file = os.path.join(self.launcher.project_path, "queue.log")
        with open(queue_log_file, "w") as f:
            f.write("")
        self.logger.info(
            "Start to monitor the queue... You can check the queue at: <{}>".format(
                queue_log_file
            )
        )

        start_time = time.time()
        last_print_time = 0
        job_running = False

        while True:
            time.sleep(0.25)
            if os.path.exists(
                os.path.join(self.launcher.project_path, "{}.log".format(job_name))
            ):
                break
            else:
                # Get result from squeue -p {{PARTITION_NAME}}
                result = subprocess.run(
                    ["squeue", "-p", "gpu" if self.launcher.use_gpu is True else "cpu"],
                    capture_output=True,
                )
                df = result.stdout.decode("utf-8").split("\n")

                try:
                    users = list(
                        map(
                            lambda row: row[: len(df[0].split("ST")[0])][:-1].split(
                                " "
                            )[-1],
                            df,
                        )
                    )
                    status = list(
                        map(
                            lambda row: row[len(df[0].split("ST")[0]) :]
                            .strip()
                            .split(" ")[0],
                            df,
                        )
                    )
                    nodes = list(
                        map(
                            lambda row: row[len(df[0].split("NODE")[0]) :]
                            .strip()
                            .split(" ")[0],
                            df,
                        )
                    )
                    node_list = list(
                        map(
                            lambda row: row[len(df[0].split("NODELIST(REASON)")[0]) :],
                            df,
                        )
                    )

                    to_queue = list(
                        zip(
                            users,
                            status,
                            nodes,
                            node_list,
                        )
                    )[1:]

                    # Check if our job is running (status "R")
                    if job_id and not job_running:
                        job_position = None
                        total_jobs = len(to_queue)

                        for i, (user, stat, node_count, node_lst) in enumerate(
                            to_queue
                        ):
                            # Find our job by checking job IDs in squeue output
                            if i < len(df) - 1:
                                job_line = df[i + 1]
                                if job_id in job_line:
                                    if stat == "R":
                                        job_running = True
                                        # Get head node
                                        head_node = self._get_head_node_from_job_id(
                                            job_id
                                        )
                                        if head_node:
                                            self.logger.info(
                                                f"Job is running on node {head_node}."
                                            )
                                            self.logger.info(
                                                f"Dashboard should be accessible at http://{head_node}:8888 (if running on cluster)"
                                            )
                                    else:
                                        job_position = i + 1
                                    break

                        if job_running:
                            break

                        # Print queue status periodically
                        if time.time() - last_print_time > 30:
                            position_str = (
                                f"{job_position}/{total_jobs}"
                                if job_position
                                else "unknown"
                            )
                            print(
                                f"Waiting for job... (Position in queue : {position_str})"
                            )
                            last_print_time = time.time()

                    # Update the queue log
                    if time.time() - start_time > 60:
                        start_time = time.time()
                        # Log to file only, no print
                        with open(queue_log_file, "a") as f:
                            f.write(f"Update time: {time.strftime('%H:%M:%S')}\n")

                    if current_queue is None or current_queue != to_queue:
                        current_queue = to_queue
                        with open(queue_log_file, "w") as f:
                            text = f"Current queue ({time.strftime('%H:%M:%S')}):\n"
                            format_row = "{:>30}" * (len(current_queue[0]))
                            for user, status, nodes, node_list in current_queue:
                                text += (
                                    format_row.format(user, status, nodes, node_list)
                                    + "\n"
                                )
                            text += "\n"
                            f.write(text)
                except Exception as e:
                    # If squeue format changes or fails parsing, don't crash
                    pass

        # Wait for the job to finish while printing the log
        self.logger.info("Job started! Waiting for the job to finish...")
        log_cursor_position = 0
        job_finished = False
        while not job_finished:
            time.sleep(0.25)
            if os.path.exists(os.path.join(self.launcher.project_path, "result.pkl")):
                job_finished = True
            else:
                with open(
                    os.path.join(self.launcher.project_path, "{}.log".format(job_name)),
                    "r",
                ) as f:
                    f.seek(log_cursor_position)
                    text = f.read()
                    if text != "":
                        print(text, end="")
                        self.logger.info(text.strip())
                    log_cursor_position = f.tell()

        self.logger.info("Job finished!")

    def _get_head_node_from_job_id(
        self, job_id: str, ssh_client: paramiko.SSHClient = None
    ) -> str:
        """Get the head node name from a SLURM job ID"""
        try:
            # Execute scontrol show job
            if ssh_client:
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"scontrol show job {job_id}"
                )
                output = stdout.read().decode("utf-8")
                if stderr.read().decode("utf-8"):
                    return None
            else:
                result = subprocess.run(
                    ["scontrol", "show", "job", job_id],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    return None
                output = result.stdout

            # Extract NodeList from output
            node_list_match = re.search(r"NodeList=([^\s]+)", output)
            if not node_list_match:
                return None

            node_list = node_list_match.group(1)

            # Get hostnames from NodeList using scontrol show hostnames
            if ssh_client:
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"scontrol show hostnames {node_list}"
                )
                hostnames_output = stdout.read().decode("utf-8")
                if stderr.read().decode("utf-8"):
                    return None
            else:
                result = subprocess.run(
                    ["scontrol", "show", "hostnames", node_list],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    return None
                output = result.stdout

            # Get first hostname (head node)
            hostnames = hostnames_output.strip().split("\n")
            if hostnames and hostnames[0]:
                return hostnames[0].strip()

            return None
        except Exception as e:
            self.logger.warning(f"Failed to get head node from job ID {job_id}: {e}")
            return None

    def _launch_server(self, cancel_old_jobs: bool = True, wait: bool = True):
        """Launch the server on the cluster and run the function using the ressources."""
        connected = False
        self.logger.info("Connecting to the cluster...")
        ssh_client = paramiko.SSHClient()
        self.ssh_client = ssh_client
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        while not connected:
            try:
                if self.launcher.server_password is None:
                    # Add ssh key
                    self.launcher.server_password = getpass(
                        "Enter your cluster password: "
                    )

                ssh_client.connect(
                    hostname=self.launcher.server_ssh,
                    username=self.launcher.server_username,
                    password=self.launcher.server_password,
                )
                ssh_client.connect(
                    hostname=self.launcher.server_ssh,
                    username=self.launcher.server_username,
                    password=self.launcher.server_password,
                )
                self._sftp_client = None # Reset SFTP
                sftp = self.get_sftp()
                connected = True
            except paramiko.ssh_exception.AuthenticationException:
                self.launcher.server_password = None
                self.logger.warning("Wrong password, please try again.")

        # Setup pyenv Python version if available
        self.pyenv_python_cmd = None
        if hasattr(self.launcher, "local_python_version"):
            self.pyenv_python_cmd = self._setup_pyenv_python(
                ssh_client, self.launcher.local_python_version
            )

        # Check Python version compatibility (with pyenv if available)
        is_compatible = self._check_python_version_compatibility(
            ssh_client, self.pyenv_python_cmd
        )
        self.python_version_compatible = is_compatible

        # Define project directory on cluster (organized by project name)
        project_dir = f"slurmray-server/{self.launcher.project_name}"

        # Write server script
        self._write_server_script()

        self.logger.info("Downloading server...")

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
            self.logger.info("Force reinstall enabled: removing existing virtualenv...")
            ssh_client.exec_command(f"rm -rf {project_dir}/.venv")
            should_recreate_venv = True
        elif os.path.exists(req_file):
            with open(req_file, "r") as f:
                req_lines = f.readlines()
            # Check remote hash (if venv exists on remote)
            remote_hash_file = f"{project_dir}/.slogs/venv_hash.txt"
            stdin, stdout, stderr = ssh_client.exec_command(
                f"test -f {remote_hash_file} && cat {remote_hash_file} || echo ''"
            )
            remote_hash = stdout.read().decode("utf-8").strip()
            current_hash = dep_manager.compute_requirements_hash(req_lines)

            if remote_hash and remote_hash == current_hash:
                # Hash matches, check if venv exists
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"test -d {project_dir}/.venv && echo exists || echo missing"
                )
                venv_exists = stdout.read().decode("utf-8").strip() == "exists"
                if venv_exists:
                    should_recreate_venv = False
                    self.logger.info(
                        "Virtualenv can be reused (requirements hash matches)"
                    )

        # Optimize requirements
        # Assuming standard path structure on Slurm cluster (Curnagl)
        venv_cmd = (
            f"cd {project_dir} && source .venv/bin/activate &&"
            if not should_recreate_venv
            else ""
        )
        req_file_to_push = self._optimize_requirements(ssh_client, venv_cmd)

        # Copy files from the project to the server
        for file in os.listdir(self.launcher.project_path):
            if file.endswith(".py") or file.endswith(".pkl") or file.endswith(".sh"):
                if file == "requirements.txt":
                    continue
                sftp.put(os.path.join(self.launcher.project_path, file), file)

        # Smart cleanup: preserve venv if hash matches, only clean server logs
        ssh_client.exec_command(f"mkdir -p {project_dir}/.slogs/server")
        if should_recreate_venv:
            # Clean server logs only (venv will be recreated by script if needed)
            ssh_client.exec_command(f"rm -rf {project_dir}/.slogs/server/*")
            # Create flag file to force venv recreation in script
            if self.launcher.force_reinstall_venv:
                ssh_client.exec_command(f"touch {project_dir}/.force_reinstall")
            self.logger.info(
                "Virtualenv will be recreated if needed (requirements changed or missing)"
            )
        else:
            # Clean server logs only, preserve venv
            ssh_client.exec_command(f"rm -rf {project_dir}/.slogs/server/*")
            # Remove flag file if it exists
            ssh_client.exec_command(f"rm -f {project_dir}/.force_reinstall")
            self.logger.info("Preserving virtualenv (requirements unchanged)")
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
            self._sync_local_files_incremental(
                sftp, project_dir, valid_files, ssh_client
            )

        # Copy the requirements.txt (optimized) to the server
        sftp.put(req_file_to_push, "requirements.txt")

        # Store venv hash on remote for future checks
        if os.path.exists(req_file):
            with open(req_file, "r") as f:
                req_lines = f.readlines()
            current_hash = dep_manager.compute_requirements_hash(req_lines)
            # Ensure .slogs directory exists on remote
            ssh_client.exec_command(f"mkdir -p {project_dir}/.slogs")
            stdin, stdout, stderr = ssh_client.exec_command(
                f"echo '{current_hash}' > {project_dir}/.slogs/venv_hash.txt"
            )
            stdout.channel.recv_exit_status()
            # Also store locally
            dep_manager.store_venv_hash(current_hash)

        # Update retention timestamp
        self._update_retention_timestamp(
            ssh_client, project_dir, self.launcher.retention_days
        )

        # Write and copy the server script to the server
        self._write_slurmray_server_sh()
        sftp.put(
            os.path.join(self.launcher.project_path, "slurmray_server.sh"),
            "slurmray_server.sh",
        )
        # Chmod script
        sftp.chmod("slurmray_server.sh", 0o755)

        # Run the server
        self.logger.info("Running server...")
        stdin, stdout, stderr = ssh_client.exec_command("./slurmray_server.sh")

        # Read the output in real time and capture job ID
        job_id = None
        tunnel = None
        output_lines = []

        # Read output line by line to capture job ID
        while True:
            line = stdout.readline()
            if not line:
                break
            output_lines.append(line)

            # Double output: console + log file
            print(line, end="")
            self.logger.info(line.strip())

            # Try to extract job ID from output (format: "Submitted batch job 12345")
            if not job_id:
                match = re.search(r"Submitted batch job (\d+)", line)
                if match:
                    job_id = match.group(1)
                    self.job_id = job_id
                    self.logger.info(f"Job ID detected: {job_id}")

        exit_status = stdout.channel.recv_exit_status()

        # Check if script failed - fail-fast immediately
        if exit_status != 0:
            # Collect error information
            stderr_output = stderr.read().decode("utf-8")
            error_msg = f"Server script exited with non-zero status: {exit_status}"
            if stderr_output.strip():
                error_msg += f"\nScript errors:\n{stderr_output}"

            # Log the error
            self.logger.error(error_msg)

            # Close tunnel if open
            if tunnel:
                try:
                    tunnel.__exit__(None, None, None)
                except Exception:
                    pass

            # Raise exception immediately (fail-fast)
            raise RuntimeError(error_msg)

        # If job ID not found in output, try to find it via squeue
        if not job_id:
            self.logger.info("Job ID not found in output, trying to find via squeue...")
            stdin, stdout, stderr = ssh_client.exec_command(
                f"squeue -u {self.launcher.server_username} -o '%i %j' --noheader"
            )
            squeue_output = stdout.read().decode("utf-8")
            # Try to find job matching project name pattern
            if self.launcher.project_name:
                for line in squeue_output.strip().split("\n"):
                    parts = line.strip().split()
                    if len(parts) >= 2 and self.launcher.project_name in parts[1]:
                        job_id = parts[0]
                        self.job_id = job_id
                        self.logger.info(f"Found job ID via squeue: {job_id}")
                        break

        # If job ID found and we are not waiting, return it and stop
        if job_id and not wait:
            self.logger.info("Async mode: Job submitted with ID {}. Disconnecting...".format(job_id))
            return job_id
        
        # If no job ID found and not waiting? We should probably warn or return None
        if not job_id and not wait:
             self.logger.warning("Async mode: Could not detect job ID. Returning None.")
             return None

        # Loop for monitoring (only if wait=True)

        # If job ID found, wait for job to be running and set up tunnel
        if job_id:
            self.logger.info(f"Waiting for job {job_id} to start running...")
            max_wait_time = 300  # Wait up to 5 minutes
            wait_start = time.time()
            job_running = False

            while time.time() - wait_start < max_wait_time:
                time.sleep(2)
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"squeue -j {job_id} -o '%T' --noheader"
                )
                status_output = stdout.read().decode("utf-8").strip()
                if status_output == "R":
                    job_running = True
                    break

            if job_running:
                # Get head node
                head_node = self._get_head_node_from_job_id(job_id, ssh_client)
                if head_node:
                    self.logger.info(
                        f"Job is running on node {head_node}. Setting up SSH tunnel for dashboard..."
                    )
                    try:
                        tunnel = SSHTunnel(
                            ssh_host=self.launcher.server_ssh,
                            ssh_username=self.launcher.server_username,
                            ssh_password=self.launcher.server_password,
                            remote_host=head_node,
                            local_port=8888,
                            remote_port=8265,
                            logger=self.logger,
                        )
                        tunnel.__enter__()
                        self.logger.info(
                            "Dashboard accessible at http://localhost:8888"
                        )

                        # Wait for job to complete while maintaining tunnel
                        # Check periodically if job is still running
                        while True:
                            time.sleep(5)
                            stdin, stdout, stderr = ssh_client.exec_command(
                                f"squeue -j {job_id} -o '%T' --noheader"
                            )
                            status_output = stdout.read().decode("utf-8").strip()
                            if status_output != "R":
                                # Job finished or no longer running
                                break
                    except Exception as e:
                        self.logger.warning(f"Failed to create SSH tunnel: {e}")
                        self.logger.info(
                            "Dashboard will not be accessible via port forwarding"
                        )
                        tunnel = None
            else:
                self.logger.warning(
                    "Job did not start running within timeout, skipping tunnel setup"
                )

        # Close tunnel if it was created
        if tunnel:
            tunnel.__exit__(None, None, None)

        # Downloading result
        self.logger.info("Downloading result...")
        project_dir = f"slurmray-server/{self.launcher.project_name}"
        try:
            sftp.get(
                f"{project_dir}/.slogs/server/result.pkl",
                os.path.join(self.launcher.project_path, "result.pkl"),
            )
            self.logger.info("Result downloaded!")

            # Clean up remote temporary files (preserve venv and cache)
            self.logger.info("Cleaning up remote temporary files...")
            ssh_client.exec_command(
                f"cd {project_dir} && "
                "find . -maxdepth 1 -type f \\( -name '*.py' -o -name '*.pkl' -o -name '*.sh' \\) "
                "! -name 'requirements.txt' -delete 2>/dev/null || true && "
                "rm -rf .slogs/server 2>/dev/null || true"
            )

            # Clean up local temporary files after successful download
            self._cleanup_local_temp_files()

        except FileNotFoundError:
            # Check for errors
            stderr_lines = stderr.readlines()
            if stderr_lines:
                self.logger.error("Errors:")
                for line in stderr_lines:
                    print(line, end="")
                    self.logger.error(line.strip())
                self.logger.error("An error occured, please check the logs.")

    def _cleanup_local_temp_files(self):
        """Clean up local temporary files after successful execution"""
        temp_files = [
            "func_source.py",
            "func_name.txt",
            "func.pkl",
            "args.pkl",
            "result.pkl",
            "spython.py",
            "sbatch.sh",
            "slurmray_server.py",
            "requirements_to_install.txt",
        ]

        for temp_file in temp_files:
            file_path = os.path.join(self.launcher.project_path, temp_file)
            if os.path.exists(file_path):
                os.remove(file_path)
                self.logger.debug(f"Removed temporary file: {temp_file}")

    def _write_server_script(self):
        """This funtion will write a script with the given specifications to run slurmray on the cluster"""
        self.logger.info("Writing slurmray server script...")
        template_file = os.path.join(
            self.launcher.module_path, "assets", "slurmray_server_template.py"
        )

        MODULES = self.launcher.modules
        NODE_NBR = self.launcher.node_nbr
        USE_GPU = self.launcher.use_gpu
        MEMORY = self.launcher.memory
        MAX_RUNNING_TIME = self.launcher.max_running_time

        # ===== Modified the template script =====
        with open(template_file, "r") as f:
            text = f.read()
        text = text.replace("{{MODULES}}", str(MODULES))
        text = text.replace("{{NODE_NBR}}", str(NODE_NBR))
        text = text.replace("{{USE_GPU}}", str(USE_GPU))
        text = text.replace("{{MEMORY}}", str(MEMORY))
        text = text.replace("{{MAX_RUNNING_TIME}}", str(MAX_RUNNING_TIME))

        # ===== Save the script =====
        script_file = "slurmray_server.py"
        with open(os.path.join(self.launcher.project_path, script_file), "w") as f:
            f.write(text)

    def _write_slurmray_server_sh(self):
        """Write the slurmray_server.sh script with pyenv support if available"""
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

        # Filter out python module from modules list if using pyenv
        modules_list = self.launcher.modules.copy()
        if use_pyenv:
            modules_list = [m for m in modules_list if not m.startswith("python")]

        modules_str = " ".join(modules_list) if modules_list else ""
        project_dir = f"slurmray-server/{self.launcher.project_name}"

        script_content = f"""#!/bin/sh

echo "Installing slurmray server"

# Copy files
mv -t {project_dir} requirements.txt slurmray_server.py
mv -t {project_dir}/.slogs/server func.pkl args.pkl 
cd {project_dir}

# Load modules
# Using specific versions for Curnagl compatibility (SLURM 24.05.3)
# gcc/13.2.0: Latest GCC version
# python module is loaded only if pyenv is not available
# cuda/12.6.2: Latest CUDA version
# cudnn/9.2.0.82-12: Compatible with cuda/12.6.2
"""

        if modules_str:
            script_content += f"module load {modules_str}\n"

        script_content += f"""
# Setup pyenv if available
"""

        if use_pyenv:
            script_content += f"""# Using pyenv for Python version management
export PATH="$HOME/.pyenv/bin:/usr/local/bin:/opt/pyenv/bin:$PATH"
{pyenv_setup}
"""
        else:
            script_content += """# pyenv not available, using system Python
"""

        script_content += f"""
# Create venv if it doesn't exist (hash check is done in Python before file upload)
# If venv needs recreation, it has already been removed by Python
# Check for force reinstall flag
if [ -f ".force_reinstall" ]; then
    echo "Force reinstall flag detected: removing existing virtualenv..."
    rm -rf .venv
    rm -f .force_reinstall
fi

if [ ! -d ".venv" ]; then
    echo "Creating virtualenv..."
"""

        if use_pyenv:
            script_content += f"""    {pyenv_setup} && {python3_cmd} -m venv .venv
"""
        else:
            script_content += f"""    {python3_cmd} -m venv .venv
"""

        script_content += f"""else
    echo "Using existing virtualenv (requirements unchanged)..."
    VENV_EXISTED=true
fi

source .venv/bin/activate

# Install requirements if file exists and is not empty
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

# Fix torch bug (https://github.com/pytorch/pytorch/issues/111469)
PYTHON_VERSION=$({python3_cmd} -c 'import sys; print(f"{{sys.version_info.major}}.{{sys.version_info.minor}}")')
export LD_LIBRARY_PATH=$HOME/{project_dir}/.venv/lib/python$PYTHON_VERSION/site-packages/nvidia/nvjitlink/lib:$LD_LIBRARY_PATH


# Run server
"""

        if use_pyenv:
            script_content += f"""{pyenv_setup} && {python_cmd} -u slurmray_server.py
"""
        else:
            script_content += f"""{python_cmd} -u slurmray_server.py
"""

        script_file = "slurmray_server.sh"
        with open(os.path.join(self.launcher.project_path, script_file), "w") as f:
            f.write(script_content)

    def _push_file(
        self, file_path: str, sftp: paramiko.SFTPClient, ssh_client: paramiko.SSHClient
    ):
        """Push a file to the cluster"""
        self.logger.info(
            f"Pushing file {os.path.basename(file_path)} to the cluster..."
        )

        # Determine the path to the file
        local_path = file_path
        local_path_from_pwd = os.path.relpath(local_path, self.launcher.pwd_path)
        cluster_path = os.path.join(
            "/users",
            self.launcher.server_username,
            "slurmray-server",
            self.launcher.project_name,
            local_path_from_pwd,
        )

        # Create the directory if not exists

        stdin, stdout, stderr = ssh_client.exec_command(
            f"mkdir -p '{os.path.dirname(cluster_path)}'"
        )
        while True:
            line = stdout.readline()
            if not line:
                break
            # Keep print for real-time feedback on directory creation (optional, could be logger.debug)
            self.logger.debug(line.strip())
        time.sleep(1)  # Wait for the directory to be created

        sftp.put(file_path, cluster_path)

    def get_result(self, job_id: str) -> Any:
        """Get result for a specific job ID"""
        # Load local result if available (cluster mode or already downloaded)
        local_path = os.path.join(self.launcher.project_path, "result.pkl")
        if os.path.exists(local_path):
             with open(local_path, "rb") as f:
                   return dill.load(f)

        # If clustered/server run, try to fetch it
        if self.launcher.cluster:
             # Already checked local path, so it's missing
             return None
             
        if self.launcher.server_run:
             self._connect()
             try:
                 project_dir = f"slurmray-server/{self.launcher.project_name}"
                 remote_path = f"{project_dir}/.slogs/server/result.pkl"
                 self.get_sftp().get(remote_path, local_path)
                 with open(local_path, "rb") as f:
                      return dill.load(f)
             except Exception:
                 return None
        
        return None

    def get_logs(self, job_id: str) -> Any:
        """Get logs for a specific job ID"""
        if not job_id:
            yield "No Job ID provided."
            return

        # Attempt to get job info to find log file
        cmd = f"scontrol show job {job_id}"
        
        output = ""
        if self.launcher.cluster:
            try:
                res = subprocess.run(cmd.split(), capture_output=True, text=True)
                output = res.stdout
            except Exception as e:
                yield f"Error querying local scontrol: {e}"
        elif self.launcher.server_run:
            self._connect()
            try:
                stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
                output = stdout.read().decode("utf-8")
            except Exception as e:
                yield f"Error querying remote job info: {e}"
                return
        else:
            yield "Not running on cluster."
            return

        # Extract JobName
        # JobName=example_1012-14h22
        import re
        match = re.search(r"JobName=([^\s]+)", output)
        if match:
             job_name = match.group(1)
             log_filename = f"{job_name}.log"
        else:
             yield "Could not determine log filename via scontrol (Job might be finished). Checking standard path..."
             # If scontrol failed (job finished), we might just look for ANY log file or standard naming
             # BUT standard naming includes timestamp. We can't guess it easily without listing.
             # We can list files matching project name and take newest.
             log_filename = None
             
             # Attempt to find log file by listing
             find_cmd = f"ls -t {self.launcher.project_name}*.log | head -n 1"
             if self.launcher.cluster:
                 if os.path.exists(self.launcher.project_path):
                     import glob
                     files = glob.glob(os.path.join(self.launcher.project_path, f"{self.launcher.project_name}*.log"))
                     if files:
                         log_filename = os.path.basename(max(files, key=os.path.getmtime))
             elif self.launcher.server_run:
                 project_dir = f"slurmray-server/{self.launcher.project_name}"
                 stdin, stdout, stderr = self.ssh_client.exec_command(f"cd {project_dir} && ls -t {self.launcher.project_name}*.log | head -n 1")
                 possible_log = stdout.read().decode("utf-8").strip()
                 if possible_log:
                     log_filename = possible_log

        if not log_filename:
             yield "Log file could not be found."
             return

        # Read log file
        if self.launcher.cluster:
             log_path = os.path.join(self.launcher.project_path, log_filename)
             if os.path.exists(log_path):
                 with open(log_path, "r") as f:
                     yield from f
             else:
                 yield f"Log file {log_path} not found."
        elif self.launcher.server_run:
             project_dir = f"slurmray-server/{self.launcher.project_name}"
             remote_log = f"{project_dir}/{log_filename}"
             try:
                 stdin, stdout, stderr = self.ssh_client.exec_command(f"cat {remote_log}")
                 # Stream output? stdout is a channel.
                 for line in stdout:
                     yield line
             except Exception as e:
                 yield f"Error reading remote log: {e}"
