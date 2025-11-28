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
from slurmray.utils import SSHTunnel

class SlurmBackend(ClusterBackend):
    """Backend for Slurm cluster execution (local or remote via SSH)"""

    def __init__(self, launcher):
        super().__init__(launcher)
        self.ssh_client = None
        self.job_id = None

    def run(self, cancel_old_jobs: bool = True) -> Any:
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
            if not hasattr(self, 'script_file'):
                 self._write_python_script()
                 self.script_file, self.job_name = self._write_slurm_script()

            self._launch_job(self.script_file, self.job_name)
            
        elif self.launcher.server_run:
            self._launch_server(cancel_old_jobs)
        
        # Load the result
        # Note: In server_run mode, _launch_server downloads result.pkl
        # In cluster mode, we wait for result.pkl
        
        if self.launcher.cluster:
             # Wait for result in cluster mode (same filesystem)
            while not os.path.exists(os.path.join(self.launcher.project_path, "result.pkl")):
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
                    check=False
                )
                self.logger.info(f"Job {job_id} canceled.")
            except Exception as e:
                self.logger.error(f"Failed to cancel job {job_id}: {e}")
        elif self.launcher.server_run and self.ssh_client:
            self.logger.info(f"Canceling remote job {job_id} via SSH...")
            try:
                # Check if connection is still active
                if self.ssh_client.get_transport() and self.ssh_client.get_transport().is_active():
                    self.ssh_client.exec_command(f"scancel {job_id}")
                    self.logger.info(f"Remote job {job_id} canceled.")
                else:
                    self.logger.warning("SSH connection lost, cannot cancel remote job.")
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
            local_mode = f"\n\taddress='auto',\n\tinclude_dashboard=True,\n\tdashboard_host='0.0.0.0',\n\tdashboard_port=8265,\nruntime_env = {self.launcher.runtime_env},\n"
        text = text.replace(
            "{{LOCAL_MODE}}",
            local_mode,
        )
        with open(os.path.join(self.launcher.project_path, "spython.py"), "w") as f:
            f.write(text)

    def _write_slurm_script(self):
        """Write the slurm script that will be executed by the job"""
        self.logger.info("Writing slurm script...")
        template_file = os.path.join(self.launcher.module_path, "assets", "sbatch_template.sh")

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
        text = text.replace(JOB_NAME, os.path.join(self.launcher.project_path, job_name))
        text = text.replace(NUM_NODES, str(self.launcher.node_nbr))
        text = text.replace(MEMORY, str(self.launcher.memory))
        text = text.replace(RUNNING_TIME, str(max_time))
        text = text.replace(PARTITION_NAME, str("gpu" if self.launcher.use_gpu > 0 else "cpu"))
        text = text.replace(
            COMMAND_PLACEHOLDER, str(f"{sys.executable} {self.launcher.project_path}/spython.py")
        )
        text = text.replace(LOAD_ENV, str(f"module load {' '.join(self.launcher.modules)}"))
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
                            lambda row: row[: len(df[0].split("ST")[0])][:-1].split(" ")[
                                -1
                            ],
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
                        map(lambda row: row[len(df[0].split("NODELIST(REASON)")[0]) :], df)
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
                        
                        for i, (user, stat, node_count, node_lst) in enumerate(to_queue):
                            # Find our job by checking job IDs in squeue output
                            if i < len(df) - 1:
                                job_line = df[i + 1]
                                if job_id in job_line:
                                    if stat == "R":
                                        job_running = True
                                        # Get head node
                                        head_node = self._get_head_node_from_job_id(job_id)
                                        if head_node:
                                            self.logger.info(f"Job is running on node {head_node}.")
                                            self.logger.info(f"Dashboard should be accessible at http://{head_node}:8888 (if running on cluster)")
                                    else:
                                        job_position = i + 1
                                    break
                        
                        if job_running:
                            break
                            
                        # Print queue status periodically
                        if time.time() - last_print_time > 30:
                            position_str = f"{job_position}/{total_jobs}" if job_position else "unknown"
                            print(f"Waiting for job... (Position in queue : {position_str})")
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
                                    format_row.format(user, status, nodes, node_list) + "\n"
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
                    os.path.join(self.launcher.project_path, "{}.log".format(job_name)), "r"
                ) as f:
                    f.seek(log_cursor_position)
                    text = f.read()
                    if text != "":
                        print(text, end="")
                        self.logger.info(text.strip())
                    log_cursor_position = f.tell()

        self.logger.info("Job finished!")

    def _get_head_node_from_job_id(self, job_id: str, ssh_client: paramiko.SSHClient = None) -> str:
        """Get the head node name from a SLURM job ID"""
        try:
            # Execute scontrol show job
            if ssh_client:
                stdin, stdout, stderr = ssh_client.exec_command(f"scontrol show job {job_id}")
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
                stdin, stdout, stderr = ssh_client.exec_command(f"scontrol show hostnames {node_list}")
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

    def _launch_server(self, cancel_old_jobs: bool = True):
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
                    self.launcher.server_password = getpass("Enter your cluster password: ")

                ssh_client.connect(
                    hostname=self.launcher.server_ssh,
                    username=self.launcher.server_username,
                    password=self.launcher.server_password,
                )
                sftp = ssh_client.open_sftp()
                connected = True
            except paramiko.ssh_exception.AuthenticationException:
                self.launcher.server_password = None
                self.logger.warning("Wrong password, please try again.")

        # Write server script
        self._write_server_script()

        self.logger.info("Downloading server...")
        
        # Generate requirements
        self._generate_requirements()
        
        # Add slurmray (unpinned for now to match legacy behavior, but could be pinned)
        with open(f"{self.launcher.project_path}/requirements.txt", "a") as f:
            f.write("slurmray\n")
            
        # Optimize requirements
        # Assuming standard path structure on Slurm cluster (Curnagl)
        venv_cmd = "cd slurmray-server && source .venv/bin/activate &&"
        req_file_to_push = self._optimize_requirements(self.ssh_client, venv_cmd)

        # Copy files from the project to the server
        for file in os.listdir(self.launcher.project_path):
            if file.endswith(".py") or file.endswith(".pkl") or file.endswith(".sh"):
                if file == "requirements.txt":
                    continue
                sftp.put(os.path.join(self.launcher.project_path, file), file)

        # Create the server directory and remove old files
        ssh_client.exec_command(
            "mkdir -p slurmray-server/.slogs/server && rm -rf slurmray-server/.slogs/server/*"
        )
        # Copy user files to the server
        for file in self.launcher.files:
            self._push_file(file, sftp, ssh_client)
            
        # Copy the requirements.txt (optimized) to the server
        sftp.put(
            req_file_to_push, "requirements.txt"
        )
        
        # Copy the server script to the server
        sftp.put(
            os.path.join(self.launcher.module_path, "assets", "slurmray_server.sh"),
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

        stdout.channel.recv_exit_status()
        
        # If job ID not found in output, try to find it via squeue
        if not job_id:
            self.logger.info("Job ID not found in output, trying to find via squeue...")
            stdin, stdout, stderr = ssh_client.exec_command(f"squeue -u {self.launcher.server_username} -o '%i %j' --noheader")
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
        
        # If job ID found, wait for job to be running and set up tunnel
        if job_id:
            self.logger.info(f"Waiting for job {job_id} to start running...")
            max_wait_time = 300  # Wait up to 5 minutes
            wait_start = time.time()
            job_running = False
            
            while time.time() - wait_start < max_wait_time:
                time.sleep(2)
                stdin, stdout, stderr = ssh_client.exec_command(f"squeue -j {job_id} -o '%T' --noheader")
                status_output = stdout.read().decode("utf-8").strip()
                if status_output == "R":
                    job_running = True
                    break
            
            if job_running:
                # Get head node
                head_node = self._get_head_node_from_job_id(job_id, ssh_client)
                if head_node:
                    self.logger.info(f"Job is running on node {head_node}. Setting up SSH tunnel for dashboard...")
                    try:
                        tunnel = SSHTunnel(
                            ssh_host=self.launcher.server_ssh,
                            ssh_username=self.launcher.server_username,
                            ssh_password=self.launcher.server_password,
                            remote_host=head_node,
                            local_port=8888,
                            remote_port=8265,
                            logger=self.logger
                        )
                        tunnel.__enter__()
                        self.logger.info("Dashboard accessible at http://localhost:8888")
                        
                        # Wait for job to complete while maintaining tunnel
                        # Check periodically if job is still running
                        while True:
                            time.sleep(5)
                            stdin, stdout, stderr = ssh_client.exec_command(f"squeue -j {job_id} -o '%T' --noheader")
                            status_output = stdout.read().decode("utf-8").strip()
                            if status_output != "R":
                                # Job finished or no longer running
                                break
                    except Exception as e:
                        self.logger.warning(f"Failed to create SSH tunnel: {e}")
                        self.logger.info("Dashboard will not be accessible via port forwarding")
                        tunnel = None
            else:
                self.logger.warning("Job did not start running within timeout, skipping tunnel setup")
        
        # Close tunnel if it was created
        if tunnel:
            tunnel.__exit__(None, None, None)

        # Downloading result
        self.logger.info("Downloading result...")
        try:
            sftp.get(
                "slurmray-server/.slogs/server/result.pkl",
                os.path.join(self.launcher.project_path, "result.pkl"),
            )
            self.logger.info("Result downloaded!")
        except FileNotFoundError:
            # Check for errors
            stderr_lines = stderr.readlines()
            if stderr_lines:
                self.logger.error("Errors:")
                for line in stderr_lines:
                    print(line, end="")
                    self.logger.error(line.strip())
                self.logger.error("An error occured, please check the logs.")

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

    def _push_file(
        self, file_path: str, sftp: paramiko.SFTPClient, ssh_client: paramiko.SSHClient
    ):
        """Push a file to the cluster"""
        self.logger.info(f"Pushing file {os.path.basename(file_path)} to the cluster...")

        # Determine the path to the file
        local_path = file_path
        local_path_from_pwd = os.path.relpath(local_path, self.launcher.pwd_path)
        cluster_path = os.path.join(
            "/users", self.launcher.server_username, "slurmray-server", local_path_from_pwd
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

        # Copy the file to the server
        sftp.put(file_path, cluster_path)
