from typing import Any, Callable, List
import subprocess
import sys
import time
import os
import dill


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
        """
        # Check the parameters
        if project_name is None:
            raise ValueError("project_name cannot be None")
        if func is None:
            raise ValueError("func cannot be None")
        if not callable(func):
            raise ValueError("func must be callable")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise ValueError("args must be a dict")
        if not isinstance(modules, list):
            raise ValueError("modules must be a list")
        if not isinstance(node_nbr, int):
            raise ValueError("node_nbr must be an int")
        if not isinstance(use_gpu, int):
            raise ValueError("gpu_nbr must be an int")
        if not isinstance(memory, int):
            raise ValueError("memory must be an int")
        if not isinstance(max_running_time, int):
            raise ValueError("max_running_time must be an int")
        
        # Save the parameters
        self.project_name = project_name
        self.func = func
        self.args = args
        self.node_nbr = node_nbr
        self.use_gpu = use_gpu
        self.memory = memory
        self.max_running_time = max_running_time

        self.modules = ["gcc", "python/3.9.13"] + [
            mod for mod in modules if mod not in ["gcc", "python/3.9.13"]
        ]
        if self.use_gpu is True and "cuda" not in self.modules:
            self.modules += ["cuda/11.8.0", "cudnn"]

        # Check if this code is running on a cluster
        self.cluster = os.path.exists("/usr/bin/sbatch")

        # Create the project directory if not exists
        self.pwd_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        self.project_path = os.path.join(self.pwd_path, "logs", self.project_name)
        if not os.path.exists(self.project_path):
            os.makedirs(self.project_path)

        # Write the python script
        self.__write_python_script(self.func, self.args)

        # Write the sh script
        self.script_file, self.job_name = self.__write_slurm_script()

    def __call__(self, cancel_old_jobs: bool = True) -> Any:
        """Launch the job and return the result

        Args:
            cancel_old_jobs (bool, optional): Cancel the old jobs. Defaults to True.

        Returns:
            Any: Result of the function
        """

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

    def __write_python_script(self, func: Callable = None, args: list = None):
        """Write the python script that will be executed by the job

        Args:
            func (Callable, optional): Function to execute. Defaults to None.
            args (list, optional): Arguments of the function. Defaults to None.

        Raises:
            ValueError: If the function is not callable
        """
        print("Writing python script...")

        # Remove the old python script
        for file in os.listdir(self.project_path):
            if file.endswith(".py") or file.endswith(".pkl"):
                os.remove(os.path.join(self.project_path, file))

        # Pickle the function
        with open(os.path.join(self.project_path, "func.pkl"), "wb") as f:
            dill.dump(func, f)

        # Pickle the arguments
        if args is None:
            args = {}
        with open(os.path.join(self.project_path, "args.pkl"), "wb") as f:
            dill.dump(args, f)

        # Write the python script
        with open(os.path.join(self.pwd_path, "slurmray", "assets", "spython_template.py"), "r") as f:
            text = f.read()

        text = text.replace("{{PROJECT_PATH}}", f'"{self.project_path}"')
        text = text.replace(
            "{{LOCAL_MODE}}",
            str(
                f""
                if not self.cluster
                else "\n\taddress='auto'\n\tinclude_dashboard=True,\n\tdashboard_host='0.0.0.0',\n\tdashboard_port=8888,\n"
            ) + "num_gpus=1" if self.use_gpu is True else "",
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
        template_file = os.path.join(self.pwd_path, "slurmray", "assets", "sbatch_template.sh")

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
                    print("Current queue:")
                    # Tabulared print
                    format_row = "{:>30}" * (len(current_queue[0]))
                    for user, status, nodes, node_list in current_queue:
                        print(format_row.format(user, status, nodes, node_list))
                    print()

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



# ---------------------------------------------------------------------------- #
#                             EXAMPLE OF EXECUTION                             #
# ---------------------------------------------------------------------------- #
if __name__ == "__main__":
    import ray

    def example_func(x):
        return ray.cluster_resources(), x + 1

    launcher = RayLauncher(
        project_name="example",
        func=example_func,
        args={"x": 1},
        modules=[],
        node_nbr=1,
        use_gpu=True,
        memory=64,
        max_running_time=15,
    )

    result = launcher()
    print(result)
