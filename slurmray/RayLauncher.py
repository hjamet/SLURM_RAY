from typing import Any, Callable, List
import subprocess
import sys
import time
import os
import dill
import paramiko
from getpass import getpass
import re

dill.settings["recurse"] = True


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

        self.modules = ["gcc", "python/3.11.6"] + [
            mod for mod in modules if mod not in ["gcc", "python/3.11.6"]
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

    def __call__(self, cancel_old_jobs: bool = True, serialize: bool = True) -> Any:
        """Launch the job and return the result

        Args:
            cancel_old_jobs (bool, optional): Cancel the old jobs. Defaults to True.
            serialize (bool, optional): Serialize the function and the arguments. This should be set to False if the function is automatically called by the server. Defaults to True.

        Returns:
            Any: Result of the function
        """
        # Sereialize function and arguments
        if serialize:
            self.__serialize_func_and_args(self.func, self.args)

        if self.cluster:
            print("Cluster detected, running on cluster...")
            # Cancel the old jobs
            if cancel_old_jobs:
                print("Canceling old jobs...")
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
            print("No cluster detected, running locally...")
            subprocess.Popen(
                [sys.executable, os.path.join(self.project_path, "spython.py")]
            )

        # Load the result
        while not os.path.exists(os.path.join(self.project_path, "result.pkl")):
            time.sleep(0.25)
        with open(os.path.join(self.project_path, "result.pkl"), "rb") as f:
            result = dill.load(f)

        return result

    def __push_file(
        self, file_path: str, sftp: paramiko.SFTPClient, ssh_client: paramiko.SSHClient
    ):
        """Push a file to the cluster

        Args:
            file_path (str): Path to the file to push. This path must be **relative** to the project directory.
        """
        print(f"Pushing file {os.path.basename(file_path)} to the cluster...")

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
            print(line, end="")
        time.sleep(1)  # Wait for the directory to be created

        # Copy the file to the server
        sftp.put(file_path, cluster_path)

    def __serialize_func_and_args(self, func: Callable = None, args: list = None):
        """Serialize the function and the arguments

        Args:
            func (Callable, optional): Function to serialize. Defaults to None.
            args (list, optional): Arguments of the function. Defaults to None.
        """
        print("Serializing function and arguments...")

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
        print("Writing python script...")

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
            f"\n\taddress='auto',\n\tinclude_dashboard=True,\n\tdashboard_host='0.0.0.0',\n\tdashboard_port=8888,\nruntime_env = {self.runtime_env},\n"
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
        print("Writing slurm script...")
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

    def __launch_job(self, script_file: str = None, job_name: str = None):
        """Launch the job

        Args:
            script_file (str, optional): Name of the script file. Defaults to None.
            job_name (str, optional): Name of the job. Defaults to None.
        """
        # ===== Submit the job =====
        print("Start to submit job!")
        subprocess.Popen(["sbatch", os.path.join(self.project_path, script_file)])
        print(
            "Job submitted! Script file is at: <{}>. Log file is at: <{}>".format(
                os.path.join(self.project_path, script_file),
                os.path.join(self.project_path, "{}.log".format(job_name)),
            )
        )

        # Wait for log file to be created
        current_queue = None
        queue_log_file = os.path.join(self.project_path, "queue.log")
        with open(queue_log_file, "w") as f:
            f.write("")
        print(
            "Start to monitor the queue... You can check the queue at: <{}>".format(
                queue_log_file
            )
        )
        subprocess.Popen(
            ["tail", "-f", os.path.join(self.project_path, "{}.log".format(job_name))]
        )
        start_time = time.time()
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

                # Update the queue log
                if time.time() - start_time > 60:
                    start_time = time.time()
                    print("Update time: {}".format(time.strftime("%H:%M:%S")))

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

                        # Print the queue
                        print(text)

        # Wait for the job to finish while printing the log
        print("Job started! Waiting for the job to finish...")
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
                    log_cursor_position = f.tell()

        print("Job finished!")

    def __launch_server(self, cancel_old_jobs: bool = True):
        """Launch the server on the cluster and run the function using the ressources.

        Args:
            cancel_old_jobs (bool, optional): Whether or not to interrupt all the user's jobs on the cluster.
        """
        connected = False
        print("Connecting to the cluster...")
        ssh_client = paramiko.SSHClient()
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
                print("Wrong password, please try again.")

        # Write server script
        self.__write_server_script()

        print("Downloading server...")
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
        print("Running server...")
        stdin, stdout, stderr = ssh_client.exec_command("./slurmray_server.sh")

        # Read the output in real time
        while True:
            line = stdout.readline()
            if not line:
                break
            print(line, end="")

        stdout.channel.recv_exit_status()

        # Downloading result
        print("Downloading result...")
        try:
            sftp.get(
                "slurmray-server/.slogs/server/result.pkl",
                os.path.join(self.project_path, "result.pkl"),
            )
            print("Result downloaded!")
        except FileNotFoundError:
            # Check for errors
            stderr_lines = stderr.readlines()
            if stderr_lines:
                print("\nErrors:\n")
                for line in stderr_lines:
                    print(line, end="")
                print("An error occured, please check the logs.")

    def __write_server_script(self):
        """This funtion will write a script with the given specifications to run slurmray on the cluster"""
        print("Writing slurmray server script...")
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
