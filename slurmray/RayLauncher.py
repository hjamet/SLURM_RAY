from typing import Any, Callable, List
import subprocess
import sys
import time
import os
import dill
import paramiko
from getpass import getpass
import re
import threading
import socket
import logging
import signal


dill.settings["recurse"] = True


class SSHTunnel:
    """Context manager for SSH port forwarding using Paramiko"""
    
    def __init__(
        self,
        ssh_host: str,
        ssh_username: str,
        ssh_password: str,
        remote_host: str,
        local_port: int = 8888,
        remote_port: int = 8888,
    ):
        """Initialize SSH tunnel
        
        Args:
            ssh_host: SSH server hostname
            ssh_username: SSH username
            ssh_password: SSH password
            remote_host: Remote hostname to forward to
            local_port: Local port to bind (default: 8888)
            remote_port: Remote port to forward (default: 8888)
        """
        self.ssh_host = ssh_host
        self.ssh_username = ssh_username
        self.ssh_password = ssh_password
        self.remote_host = remote_host
        self.local_port = local_port
        self.remote_port = remote_port
        self.ssh_client = None
        self.forward_server = None
    
    def __enter__(self):
        """Create SSH tunnel"""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_client.connect(
                hostname=self.ssh_host,
                username=self.ssh_username,
                password=self.ssh_password,
            )
            
            # Create local port forwarding using socket server
            transport = self.ssh_client.get_transport()
            
            # Create a local socket server
            local_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            local_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            local_socket.bind(("127.0.0.1", self.local_port))
            local_socket.listen(5)
            self.forward_server = local_socket
            
            def forward_handler(client_socket):
                try:
                    # Create SSH channel to remote host
                    channel = transport.open_channel(
                        "direct-tcpip",
                        (self.remote_host, self.remote_port),
                        client_socket.getpeername(),
                    )
                    
                    # Forward data bidirectionally
                    def forward_data(source, dest):
                        try:
                            while True:
                                data = source.recv(1024)
                                if not data:
                                    break
                                dest.send(data)
                        except Exception:
                            pass
                        finally:
                            source.close()
                            dest.close()
                    
                    # Start forwarding in both directions
                    thread1 = threading.Thread(
                        target=forward_data,
                        args=(client_socket, channel),
                        daemon=True,
                    )
                    thread2 = threading.Thread(
                        target=forward_data,
                        args=(channel, client_socket),
                        daemon=True,
                    )
                    thread1.start()
                    thread2.start()
                    thread1.join()
                    thread2.join()
                except Exception:
                    pass
                finally:
                    client_socket.close()
            
            def accept_handler():
                while True:
                    try:
                        client_socket, addr = self.forward_server.accept()
                        thread = threading.Thread(
                            target=forward_handler,
                            args=(client_socket,),
                            daemon=True,
                        )
                        thread.start()
                    except Exception:
                        break
            
            forward_thread = threading.Thread(target=accept_handler, daemon=True)
            forward_thread.start()
            
            print(f"SSH tunnel established: localhost:{self.local_port} -> {self.remote_host}:{self.remote_port}")
            return self
        except Exception as e:
            print(f"Warning: Failed to create SSH tunnel: {e}")
            print("Dashboard will not be accessible via port forwarding")
            if self.ssh_client:
                self.ssh_client.close()
            self.ssh_client = None
            self.forward_server = None
            return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close SSH tunnel"""
        if self.forward_server:
            try:
                self.forward_server.close()
            except Exception:
                pass
        if self.ssh_client:
            self.ssh_client.close()
        return False


class RayLauncher:
    """A class that automatically connects RAY workers and executes the function requested by the user"""

    def __init__(
        self,
        project_name: str = None,
        func: Callable = None,
        args: dict = None,
        files: List[str] = [],
        modules: List[str] = [],
        node_nbr: int = 1,
        use_gpu: bool = False,
        memory: int = 64,
        max_running_time: int = 60,
        runtime_env: dict = {"env_vars": {}},
        server_run: bool = True,
        server_ssh: str = "curnagl.dcsr.unil.ch",
        server_username: str = "hjamet",
        server_password: str = None,
        log_file: str = "logs/RayLauncher.log",
    ):
        """Initialize the launcher

        Args:
            project_name (str, optional): Name of the project. Defaults to None.
            func (Callable, optional): Function to execute. This function should not be remote but can use ray ressources. Defaults to None.
            args (dict, optional): Arguments of the function. Defaults to None.
            files (List[str], optional): List of files to push to the cluster. This path must be **relative** to the project directory. Defaults to [].
            modules (List[str], optional): List of modules to load on the curnagl Cluster. Use `module spider` to see available modules. Defaults to None.
            node_nbr (int, optional): Number of nodes to use. Defaults to 1.
            use_gpu (bool, optional): Use GPU or not. Defaults to False.
            memory (int, optional): Amount of RAM to use per node in GigaBytes. Defaults to 64.
            max_running_time (int, optional): Maximum running time of the job in minutes. Defaults to 60.
            runtime_env (dict, optional): Environment variables to share between all the workers. Can be useful for issues like https://github.com/ray-project/ray/issues/418. Default to empty.
            server_run (bool, optional): If you run the launcher from your local machine, you can use this parameter to execute your function using online cluster ressources. Defaults to True.
            server_ssh (str, optional): If `server_run` is set to true, the addess of the **SLURM** server to use.
            server_username (str, optional): If `server_run` is set to true, the username with which you wish to connect.
            server_password (str, optional): If `server_run` is set to true, the password of the user to connect to the server. CAUTION: never write your password in the code. Defaults to None.
            log_file (str, optional): Path to the log file. Defaults to "logs/RayLauncher.log".
        """
        # Save the parameters
        self.project_name = project_name
        self.func = func
        self.args = args
        self.files = files
        self.node_nbr = node_nbr
        self.use_gpu = use_gpu
        self.memory = memory
        self.max_running_time = max_running_time
        self.runtime_env = runtime_env
        self.server_run = server_run
        self.server_ssh = server_ssh
        self.server_username = server_username
        self.server_password = server_password
        self.log_file = log_file
        self.job_id = None
        self.ssh_client = None

        self.__setup_logger()

        self.modules = ["gcc", "python/3.12.1"] + [
            mod for mod in modules if mod not in ["gcc", "python/3.12.1"]
        ]
        if self.use_gpu is True and "cuda" not in self.modules:
            self.modules += ["cuda", "cudnn"]

        # Check if this code is running on a cluster
        self.cluster = os.path.exists("/usr/bin/sbatch")

        # Create the project directory if not exists
        self.pwd_path = os.getcwd()
        self.module_path = os.path.dirname(os.path.abspath(__file__))
        self.project_path = os.path.join(self.pwd_path, ".slogs", self.project_name)
        if not os.path.exists(self.project_path):
            os.makedirs(self.project_path)

        if not self.server_run:
            self.__write_python_script()
            self.script_file, self.job_name = self.__write_slurm_script()

    def __setup_logger(self):
        """Setup the logger"""
        # Create the log directory if not exists
        log_dir = os.path.dirname(self.log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # Configure the logger
        self.logger = logging.getLogger(f"RayLauncher-{self.project_name}")
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplication if instantiated multiple times
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        # File handler (constantly rewritten)
        file_handler = logging.FileHandler(self.log_file, mode='w')
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

        # Console handler (only warnings and errors)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

    def _handle_signal(self, signum, frame):
        """Handle interruption signals (SIGINT, SIGTERM) to cleanup resources"""
        sig_name = signal.Signals(signum).name
        self.logger.warning(f"Signal {sig_name} received. Cleaning up resources...")
        print(f"\nInterruption received ({sig_name}). Canceling job and cleaning up...")
        
        if self.job_id:
            if self.cluster:
                self.logger.info(f"Canceling local job {self.job_id}...")
                try:
                    subprocess.run(
                        ["scancel", self.job_id],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False
                    )
                    self.logger.info(f"Job {self.job_id} canceled.")
                except Exception as e:
                    self.logger.error(f"Failed to cancel job {self.job_id}: {e}")
            elif self.server_run and self.ssh_client:
                self.logger.info(f"Canceling remote job {self.job_id} via SSH...")
                try:
                    # Check if connection is still active
                    if self.ssh_client.get_transport() and self.ssh_client.get_transport().is_active():
                        self.ssh_client.exec_command(f"scancel {self.job_id}")
                        self.logger.info(f"Remote job {self.job_id} canceled.")
                    else:
                        self.logger.warning("SSH connection lost, cannot cancel remote job.")
                except Exception as e:
                    self.logger.error(f"Failed to cancel remote job {self.job_id}: {e}")
                finally:
                    try:
                        self.ssh_client.close()
                    except Exception:
                        pass
        
        sys.exit(1)

    def __call__(self, cancel_old_jobs: bool = True, serialize: bool = True) -> Any:
        """Launch the job and return the result

        Args:
            cancel_old_jobs (bool, optional): Cancel the old jobs. Defaults to True.
            serialize (bool, optional): Serialize the function and the arguments. This should be set to False if the function is automatically called by the server. Defaults to True.

        Returns:
            Any: Result of the function
        """
        # Register signal handlers
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        try:
            # Sereialize function and arguments
            if serialize:
                self.__serialize_func_and_args(self.func, self.args)

            if self.cluster:
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
                self.__launch_job(self.script_file, self.job_name)
            elif self.server_run:
                self.__launch_server(cancel_old_jobs)
            else:
                self.logger.info("No cluster detected, running locally...")
                subprocess.Popen(
                    [sys.executable, os.path.join(self.project_path, "spython.py")]
                )

            # Load the result
            while not os.path.exists(os.path.join(self.project_path, "result.pkl")):
                time.sleep(0.25)
            with open(os.path.join(self.project_path, "result.pkl"), "rb") as f:
                result = dill.load(f)

            return result
        finally:
            # Restore original signal handlers
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)

    def __push_file(
        self, file_path: str, sftp: paramiko.SFTPClient, ssh_client: paramiko.SSHClient
    ):
        """Push a file to the cluster

        Args:
            file_path (str): Path to the file to push. This path must be **relative** to the project directory.
        """
        self.logger.info(f"Pushing file {os.path.basename(file_path)} to the cluster...")

        # Determine the path to the file
        local_path = file_path
        local_path_from_pwd = os.path.relpath(local_path, self.pwd_path)
        cluster_path = os.path.join(
            "/users", self.server_username, "slurmray-server", local_path_from_pwd
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

    def __serialize_func_and_args(self, func: Callable = None, args: list = None):
        """Serialize the function and the arguments

        Args:
            func (Callable, optional): Function to serialize. Defaults to None.
            args (list, optional): Arguments of the function. Defaults to None.
        """
        self.logger.info("Serializing function and arguments...")

        # Pickle the function
        with open(os.path.join(self.project_path, "func.pkl"), "wb") as f:
            dill.dump(func, f)

        # Pickle the arguments
        if args is None:
            args = {}
        with open(os.path.join(self.project_path, "args.pkl"), "wb") as f:
            dill.dump(args, f)

    def __write_python_script(self):
        """Write the python script that will be executed by the job"""
        self.logger.info("Writing python script...")

        # Remove the old python script
        for file in os.listdir(self.project_path):
            if file.endswith(".py"):
                os.remove(os.path.join(self.project_path, file))

        # Write the python script
        with open(
            os.path.join(self.module_path, "assets", "spython_template.py"),
            "r",
        ) as f:
            text = f.read()

        text = text.replace("{{PROJECT_PATH}}", f'"{self.project_path}"')
        local_mode = ""
        if self.cluster or self.server_run:
            local_mode = f"\n\taddress='auto',\n\tinclude_dashboard=True,\n\tdashboard_host='0.0.0.0',\n\tdashboard_port=8888,\nruntime_env = {self.runtime_env},\n"
        text = text.replace(
            "{{LOCAL_MODE}}",
            local_mode,
        )
        with open(os.path.join(self.project_path, "spython.py"), "w") as f:
            f.write(text)

    def __write_slurm_script(
        self,
    ):
        """Write the slurm script that will be executed by the job

        Returns:
            str: Name of the script file
            str: Name of the job
        """
        self.logger.info("Writing slurm script...")
        template_file = os.path.join(self.module_path, "assets", "sbatch_template.sh")

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
            self.project_name, time.strftime("%d%m-%Hh%M", time.localtime())
        )

        # Convert the time to xx:xx:xx format
        max_time = "{}:{}:{}".format(
            str(self.max_running_time // 60).zfill(2),
            str(self.max_running_time % 60).zfill(2),
            str(0).zfill(2),
        )

        # ===== Modified the template script =====
        with open(template_file, "r") as f:
            text = f.read()
        text = text.replace(JOB_NAME, os.path.join(self.project_path, job_name))
        text = text.replace(NUM_NODES, str(self.node_nbr))
        text = text.replace(MEMORY, str(self.memory))
        text = text.replace(RUNNING_TIME, str(max_time))
        text = text.replace(PARTITION_NAME, str("gpu" if self.use_gpu > 0 else "cpu"))
        text = text.replace(
            COMMAND_PLACEHOLDER, str(f"{sys.executable} {self.project_path}/spython.py")
        )
        text = text.replace(LOAD_ENV, str(f"module load {' '.join(self.modules)}"))
        text = text.replace(GIVEN_NODE, "")
        text = text.replace(COMMAND_SUFFIX, "")
        text = text.replace(
            "# THIS FILE IS A TEMPLATE AND IT SHOULD NOT BE DEPLOYED TO " "PRODUCTION!",
            "# THIS FILE IS MODIFIED AUTOMATICALLY FROM TEMPLATE AND SHOULD BE "
            "RUNNABLE!",
        )

        # ===== Add partition specifics =====
        if self.use_gpu > 0:
            text = text.replace(
                PARTITION_SPECIFICS,
                str("#SBATCH --gres gpu:1\n#SBATCH --gres-flags enforce-binding"),
            )
        else:
            text = text.replace(PARTITION_SPECIFICS, "#SBATCH --exclusive")

        # ===== Save the script =====
        script_file = "sbatch.sh"
        with open(os.path.join(self.project_path, script_file), "w") as f:
            f.write(text)

        return script_file, job_name

    def __get_head_node_from_job_id(self, job_id: str, ssh_client: paramiko.SSHClient = None) -> str:
        """Get the head node name from a SLURM job ID
        
        Args:
            job_id: SLURM job ID
            ssh_client: Optional SSH client for remote execution. If None, executes locally.
        
        Returns:
            Head node name, or None if not found
        """
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
                hostnames_output = result.stdout
            
            # Get first hostname (head node)
            hostnames = hostnames_output.strip().split("\n")
            if hostnames and hostnames[0]:
                return hostnames[0].strip()
            
            return None
        except Exception as e:
            self.logger.warning(f"Failed to get head node from job ID {job_id}: {e}")
            return None

    def __launch_job(self, script_file: str = None, job_name: str = None):
        """Launch the job

        Args:
            script_file (str, optional): Name of the script file. Defaults to None.
            job_name (str, optional): Name of the job. Defaults to None.
        """
        # ===== Submit the job =====
        self.logger.info("Start to submit job!")
        result = subprocess.run(
            ["sbatch", os.path.join(self.project_path, script_file)],
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
                os.path.join(self.project_path, script_file),
                os.path.join(self.project_path, "{}.log".format(job_name)),
            )
        )

        # Wait for log file to be created and job to start running
        current_queue = None
        queue_log_file = os.path.join(self.project_path, "queue.log")
        with open(queue_log_file, "w") as f:
            f.write("")
        self.logger.info(
            "Start to monitor the queue... You can check the queue at: <{}>".format(
                queue_log_file
            )
        )
        subprocess.Popen(
            ["tail", "-f", os.path.join(self.project_path, "{}.log".format(job_name))]
        )
        start_time = time.time()
        job_running = False
        tunnel = None
        
        while True:
            time.sleep(0.25)
            if os.path.exists(
                os.path.join(self.project_path, "{}.log".format(job_name))
            ):
                break
            else:
                # Get result from squeue -p {{PARTITION_NAME}}
                result = subprocess.run(
                    ["squeue", "-p", "gpu" if self.use_gpu is True else "cpu"],
                    capture_output=True,
                )
                df = result.stdout.decode("utf-8").split("\n")
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
                    for i, (user, stat, node_count, node_lst) in enumerate(to_queue):
                        # Find our job by checking job IDs in squeue output
                        if i < len(df) - 1:
                            job_line = df[i + 1]
                            if job_id in job_line and stat == "R":
                                job_running = True
                                # Get head node
                                head_node = self.__get_head_node_from_job_id(job_id)
                                if head_node:
                                    self.logger.info(f"Job is running on node {head_node}.")
                                    self.logger.info(f"Dashboard should be accessible at http://{head_node}:8888 (if running on cluster)")
                                break

                # Update the queue log
                if time.time() - start_time > 60:
                    start_time = time.time()
                    self.logger.info("Update time: {}".format(time.strftime("%H:%M:%S")))

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

                        # Print the queue to logger instead of print
                        self.logger.info(text)

        # Wait for the job to finish while printing the log
        self.logger.info("Job started! Waiting for the job to finish...")
        log_cursor_position = 0
        job_finished = False
        while not job_finished:
            time.sleep(0.25)
            if os.path.exists(os.path.join(self.project_path, "result.pkl")):
                job_finished = True
            else:
                with open(
                    os.path.join(self.project_path, "{}.log".format(job_name)), "r"
                ) as f:
                    f.seek(log_cursor_position)
                    text = f.read()
                    if text != "":
                        print(text, end="")
                        self.logger.info(text.strip())
                    log_cursor_position = f.tell()

        self.logger.info("Job finished!")

    def __launch_server(self, cancel_old_jobs: bool = True):
        """Launch the server on the cluster and run the function using the ressources.

        Args:
            cancel_old_jobs (bool, optional): Whether or not to interrupt all the user's jobs on the cluster.
        """
        connected = False
        self.logger.info("Connecting to the cluster...")
        ssh_client = paramiko.SSHClient()
        self.ssh_client = ssh_client
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        while not connected:
            try:
                if self.server_password is None:
                    # Add ssh key
                    self.server_password = getpass("Enter your cluster password: ")

                ssh_client.connect(
                    hostname=self.server_ssh,
                    username=self.server_username,
                    password=self.server_password,
                )
                sftp = ssh_client.open_sftp()
                connected = True
            except paramiko.ssh_exception.AuthenticationException:
                self.server_password = None
                self.logger.warning("Wrong password, please try again.")

        # Write server script
        self.__write_server_script()

        self.logger.info("Downloading server...")
        # Generate requirements.txt
        subprocess.run(
            [f"pip-chill --no-version > {self.project_path}/requirements.txt"],
            shell=True,
        )

        with open(f"{self.project_path}/requirements.txt", "r") as file:
            lines = file.readlines()
            # Adapt dependencies for the cluster
            # Adapt torch version (not needed anymore)
            # lines = [re.sub(r"torch\n", "torch==2.0.1\n", line) for line in lines]
            # lines = [re.sub(r'torchvision\n', 'torchvision --pre --index-url https://download.pytorch.org/whl/nightly/cu121\n', line) for line in lines]
            # lines = [re.sub(r'torchaudio\n', 'torchaudio --pre --index-url https://download.pytorch.org/whl/nightly/cu121\n', line) for line in lines]

            # lines = [re.sub(r'bitsandbytes\n', 'bitsandbytes --global-option="--cuda_ext"\n', line) for line in lines]
            # Solve torch buf (https://github.com/pytorch/pytorch/issues/111469)
            # if "torchaudio\n" or "torchvision\n" in lines:
            #     lines.append(
            #         "torch==2.1.1 --index-url https://download.pytorch.org/whl/cu121\n"
            #     )
            lines.append("slurmray\n")

        with open(f"{self.project_path}/requirements.txt", "w") as file:
            file.writelines(lines)

        # Copy files from the project to the server
        for file in os.listdir(self.project_path):
            if file.endswith(".py") or file.endswith(".pkl") or file.endswith(".sh"):
                sftp.put(os.path.join(self.project_path, file), file)

        # Create the server directory and remove old files
        ssh_client.exec_command(
            "mkdir -p slurmray-server/.slogs/server && rm -rf slurmray-server/.slogs/server/*"
        )
        # Copy user files to the server
        for file in self.files:
            self.__push_file(file, sftp, ssh_client)
        # Copy the requirements.txt to the server
        sftp.put(
            os.path.join(self.project_path, "requirements.txt"), "requirements.txt"
        )
        # Copy the server script to the server
        sftp.put(
            os.path.join(self.module_path, "assets", "slurmray_server.sh"),
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
            stdin, stdout, stderr = ssh_client.exec_command(f"squeue -u {self.server_username} -o '%i %j' --noheader")
            squeue_output = stdout.read().decode("utf-8")
            # Try to find job matching project name pattern
            if self.project_name:
                for line in squeue_output.strip().split("\n"):
                    parts = line.strip().split()
                    if len(parts) >= 2 and self.project_name in parts[1]:
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
                head_node = self.__get_head_node_from_job_id(job_id, ssh_client)
                if head_node:
                    self.logger.info(f"Job is running on node {head_node}. Setting up SSH tunnel for dashboard...")
                    try:
                        tunnel = SSHTunnel(
                            ssh_host=self.server_ssh,
                            ssh_username=self.server_username,
                            ssh_password=self.server_password,
                            remote_host=head_node,
                            local_port=8888,
                            remote_port=8888,
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
                os.path.join(self.project_path, "result.pkl"),
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

    def __write_server_script(self):
        """This funtion will write a script with the given specifications to run slurmray on the cluster"""
        self.logger.info("Writing slurmray server script...")
        template_file = os.path.join(
            self.module_path, "assets", "slurmray_server_template.py"
        )

        MODULES = self.modules
        NODE_NBR = self.node_nbr
        USE_GPU = self.use_gpu
        MEMORY = self.memory
        MAX_RUNNING_TIME = self.max_running_time

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
        with open(os.path.join(self.project_path, script_file), "w") as f:
            f.write(text)


# ---------------------------------------------------------------------------- #
#                             EXAMPLE OF EXECUTION                             #
# ---------------------------------------------------------------------------- #
if __name__ == "__main__":
    import ray
    import torch

    def function_inside_function():
        with open("documentation/RayLauncher.html", "r") as f:
            return f.read()[0:10]

    def example_func(x):
        result = (
            ray.cluster_resources(),
            f"GPU is available : {torch.cuda.is_available()}",
            x + 1,
            function_inside_function(),
        )
        return result

    launcher = RayLauncher(
        project_name="example",  # Name of the project (will create a directory with this name in the current directory)
        func=example_func,  # Function to execute
        args={"x": 5},  # Arguments of the function
        files=[
            "documentation/RayLauncher.html"
        ],  # List of files to push to the cluster (file path will be recreated on the cluster)
        modules=[],  # List of modules to load on the curnagl Cluster (CUDA & CUDNN are automatically added if use_gpu=True)
        node_nbr=1,  # Number of nodes to use
        use_gpu=True,  # If you need A100 GPU, you can set it to True
        memory=8,  # In MegaBytes
        max_running_time=5,  # In minutes
        runtime_env={
            "env_vars": {"NCCL_SOCKET_IFNAME": "eno1"}
        },  # Example of environment variable
        server_run=True,  # To run the code on the cluster and not locally
        server_ssh="curnagl.dcsr.unil.ch",  # Address of the SLURM server
        server_username="hjamet",  # Username to connect to the server
        server_password=None,  # Will be asked in the terminal
    )

    result = launcher()
    print(result)
