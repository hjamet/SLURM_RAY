from typing import Any, Callable, List
import subprocess
import sys
import time
import os
import dill
import paramiko
from getpass import getpass

dill.settings["recurse"] = True


class RayLauncher:
    """A class that automatically connects RAY workers and executes the function requested by the user"""

    def __init__(
        self,
        project_name: str = None,
        func: Callable = None,
        args: dict = None,
        modules: List[str] = [],
        node_nbr: int = 1,
        use_gpu: bool = False,
        memory: int = 64,
        max_running_time: int = 60,
        server_run: bool = True,
        server_ssh: str = "curnagl.dcsr.unil.ch",
        server_username: str = "hjamet",
    ):
        """Initialize the launcher

        Args:
            project_name (str, optional): Name of the project. Defaults to None.
            func (Callable, optional): Function to execute. This function should not be remote but can use ray ressources. Defaults to None.
            args (dict, optional): Arguments of the function. Defaults to None.
            modules (List[str], optional): List of modules to load on the curnagl Cluster. Use `module spider` to see available modules. Defaults to None.
            node_nbr (int, optional): Number of nodes to use. Defaults to 1.
            use_gpu (bool, optional): Use GPU or not. Defaults to False.
            memory (int, optional): Amount of RAM to use per node in GigaBytes. Defaults to 64.
            max_running_time (int, optional): Maximum running time of the job in minutes. Defaults to 60.
            server_run (bool, optional): If you run the launcher from your local machine, you can use this parameter to execute your function using online cluster ressources. Defaults to True.
            server_ssh (str, optional): If `server_run` is set to true, the addess of the **SLURM** server to use.
            server_username (str, optional): If `server_run` is set to true, the username with which you wish to connect.
        """
        # Save the parameters
        self.project_name = project_name
        self.func = func
        self.args = args
        self.node_nbr = node_nbr
        self.use_gpu = use_gpu
        self.memory = memory
        self.max_running_time = max_running_time
        self.server_run = server_run
        self.server_ssh = server_ssh
        self.server_username = server_username

        self.modules = ["gcc", "python/3.9.13"] + [
            mod for mod in modules if mod not in ["gcc", "python/3.9.13"]
        ]
        if self.use_gpu is True and "cuda" not in self.modules:
            self.modules += ["cuda/11.8.0", "cudnn"]

        # Check if this code is running on a cluster
        self.cluster = os.path.exists("/usr/bin/sbatch")

        # Create the project directory if not exists
        self.module_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".."
        )
        self.pwd_path = os.getcwd()
        self.module_path = os.path.dirname(os.path.abspath(__file__))
        self.project_path = os.path.join(self.pwd_path, ".slogs", self.project_name)
        if not os.path.exists(self.project_path):
            os.makedirs(self.project_path)

        if not self.server_run:
            self.__write_python_script()
            self.script_file, self.job_name = self.__write_slurm_script()

    def __call__(self, cancel_old_jobs: bool = True) -> Any:
        """Launch the job and return the result

        Args:
            cancel_old_jobs (bool, optional): Cancel the old jobs. Defaults to True.

        Returns:
            Any: Result of the function
        """
        # Sereialize function and arguments
        self.serialize_func_and_args(self.func, self.args)

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

    def serialize_func_and_args(self, func: Callable = None, args: list = None):
        """Serialize the function and the arguments

        Args:
            func (Callable, optional): Function to serialize. Defaults to None.
            args (list, optional): Arguments of the function. Defaults to None.
        """
        print("Serializing function and arguments...")

        # Remove the old python script
        for file in os.listdir(self.project_path):
            if file.endswith(".pkl"):
                os.remove(os.path.join(self.project_path, file))

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
        text = text.replace(
            "{{LOCAL_MODE}}",
            str(
                f""
                if not (self.cluster or self.server_run)
                else "\n\taddress='auto',\n\tinclude_dashboard=True,\n\tdashboard_host='0.0.0.0',\n\tdashboard_port=8888,\n"
            ),
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
        queue_log_file = os.path.join(
            self.project_path, "{}_queue.log".format(job_name)
        )
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
                if current_queue is None or current_queue != to_queue:
                    current_queue = to_queue
                    with open(queue_log_file, "w") as f:
                        text = "Current queue:\n"
                        format_row = "{:>30}" * (len(current_queue[0]))
                        for user, status, nodes, node_list in current_queue:
                            text += (
                                format_row.format(user, status, nodes, node_list) + "\n"
                            )
                        text += "\n"
                        f.write(text)

        # Wait for the job to finish while printing the log
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
                # Add ssh key
                ssh_key = getpass("Enter your cluster password: ")
                ssh_client.connect(
                    hostname=self.server_ssh,
                    username=self.server_username,
                    password=ssh_key,
                )
                sftp = ssh_client.open_sftp()
                connected = True
            except paramiko.ssh_exception.AuthenticationException:
                print("Wrong password, please try again.")

        # Write server script
        self.__write_server_script()

        print("Downloading server...")
        # Generate requirements.txt
        subprocess.run(
            [f"pip freeze > {self.project_path}/requirements.txt"], shell=True
        )
        # Add slurmray --pre
        with open(f"{self.project_path}/requirements.txt", "r") as file:
            requirements  = file.read()
            requirements += "\nslurmray --pre"
        # Replace pytorch version with cu118
        if "torch" in requirements:
            for m in ["torch", "torchvision", "torchaudio"]:
                requirements = requirements.replace(
                    f"\n{m}==", f"\n{m}==2.1.1+cu118"
                ) 
            

        # Copy files from the project to the server
        for file in os.listdir(self.project_path):
            if file.endswith(".py") or file.endswith(".pkl") or file.endswith(".sh"):
                sftp.put(os.path.join(self.project_path, file), file)
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

        # Downloading result
        print("Downloading result...")
        sftp.get(
            "slurmray-server/.slogs/server/result.pkl",
            os.path.join(self.project_path, "result.pkl"),
        )
        print("Result downloaded!")

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

    def function_inside_function(x):
        return ray.cluster_resources(), x + 1

    def example_func(x):
        return function_inside_function(x)

    launcher = RayLauncher(
        project_name="example",
        func=example_func,
        args={"x": 1},
        modules=[],
        node_nbr=1,
        use_gpu=False,
        memory=8,
        max_running_time=5,
        server_run=True,
        server_ssh="curnagl.dcsr.unil.ch",
        server_username="hjamet",
    )

    result = launcher()
    print(result)
