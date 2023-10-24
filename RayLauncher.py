from typing import Any, Callable
import subprocess
import sys
import time
import os
import dill

class RayLauncher:
    """A class that automatically connects RAY workers and executes the function requested by the user
    """
    def __init__(self, cpu_nbr : int = 1, gpu_nbr : int = 0, func : Callable = None, args : list = None, project_name : str = None):
        """Constructor of the class

        Args:
            cpu_nbr (int, optional): Number of CPUs to use. Defaults to 1.
            gpu_nbr (int, optional): Number of GPUs to use. Defaults to 0.
            func (Callable, optional): Function to execute. Defaults to None.
        """
        # Save the parameters
        self.cpu_nbr = cpu_nbr
        self.gpu_nbr = gpu_nbr
        self.func = func
        self.args = args
        self.project_name = project_name
        
        # Create the project directory if not exists
        self.pwd_path = os.path.dirname(os.path.abspath(__file__))
        self.project_path = os.path.join(self.pwd_path, "logs", self.project_name)
        if not os.path.exists(self.project_path):
            os.makedirs(self.project_path)
        
        # Write the python script
        self.write_python_script(self.func, self.args)
        
        # Write the sh script
        self.script_file, self.job_name = self.write_slurm_script(self.cpu_nbr, self.gpu_nbr)
        

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        # Launch the job
        self.launch_job(self.script_file, self.job_name)
        
        # Load the result
        with open(os.path.join(self.project_path, "result.pkl"), "rb") as f:
            result = dill.load(f)
            
        return result
        
    def write_python_script(self, func : Callable = None, args : list = None):
        # Remove the old python script
        for file in os.listdir(self.project_path):
            if file.endswith(".py") or file.endswith(".pkl"):
                os.remove(os.path.join(self.project_path, file))
        
        # Pickle the function
        with open(os.path.join(self.project_path, "func.pkl"), "wb") as f:
            dill.dump(func, f)
        
        # Pickle the arguments
        with open(os.path.join(self.project_path, "args.pkl"), "wb") as f:
            dill.dump(args, f)
            
        # Write the python script
        with open(os.path.join(self.pwd_path, "spython_template.py"), "r") as f:
            text = f.read()
 
        text = text.replace("{{PROJECT_PATH}}", f"\"{self.project_path}\"")
        with open(os.path.join(self.project_path, "spython.py"), "w") as f:
            f.write(text)
    
    def write_slurm_script(self, cpu_nbr : int = None, gpu_nbr : int = None):
        template_file = os.path.join(
            self.pwd_path,
            'sbatch_template.sh'
        )
        
        # Get venv location
        venv_location = os.path.dirname(sys.executable)

        JOB_NAME = "{{JOB_NAME}}"
        NUM_NODES = "{{NUM_NODES}}"
        NUM_GPUS_PER_NODE = "{{NUM_GPUS_PER_NODE}}"
        PARTITION_NAME = "{{PARTITION_NAME}}"
        COMMAND_PLACEHOLDER = "{{COMMAND_PLACEHOLDER}}"
        GIVEN_NODE = "{{GIVEN_NODE}}"
        COMMAND_SUFFIX = "{{COMMAND_SUFFIX}}"
        LOAD_ENV = "{{LOAD_ENV}}"

        job_name = "{}_{}".format(
            self.project_name,
            time.strftime("%d%m-%Hh%M", time.localtime())
        )

        # ===== Modified the template script =====
        with open(template_file, "r") as f:
            text = f.read()
        text = text.replace(JOB_NAME, os.path.join(self.project_path, job_name))
        text = text.replace(NUM_NODES, str(cpu_nbr))
        text = text.replace(NUM_GPUS_PER_NODE, str(gpu_nbr))
        text = text.replace(PARTITION_NAME, str("gpu" if gpu_nbr > 0 else "cpu"))
        text = text.replace(COMMAND_PLACEHOLDER, str(f"{sys.executable} {self.project_path}/spython.py"))
        text = text.replace(LOAD_ENV, str("module load gcc python/3.9.13"))
        text = text.replace(GIVEN_NODE, "")
        text = text.replace(COMMAND_SUFFIX, "")
        text = text.replace(
            "# THIS FILE IS A TEMPLATE AND IT SHOULD NOT BE DEPLOYED TO "
            "PRODUCTION!",
            "# THIS FILE IS MODIFIED AUTOMATICALLY FROM TEMPLATE AND SHOULD BE "
            "RUNNABLE!"
        )

        # ===== Save the script =====
        script_file = "sbatch.sh"
        with open(os.path.join(self.project_path, script_file), "w") as f:
            f.write(text)
            
        return script_file, job_name
        
    def launch_job(self, script_file : str = None, job_name : str = None):
        # ===== Submit the job =====
        print("Start to submit job!")
        subprocess.Popen(["sbatch", os.path.join(self.project_path, script_file)])
        print(
            "Job submitted! Script file is at: <{}>. Log file is at: <{}>".format(
                os.path.join(self.project_path, script_file),
                os.path.join(self.project_path, "{}.log".format(job_name)))
        )
        
        # Wait for the job to finish
        while True:
            time.sleep(1)
            if os.path.exists(os.path.join(self.project_path, "result.pkl")):
                break
        print("Job finished!")

        
# ---------------------------------------------------------------------------- #
#                             EXAMPLE OF EXECUTION                             #
# ---------------------------------------------------------------------------- #
if __name__ == "__main__":
    def test_func(x):
        return "Number of CPUs: {}".format(os.cpu_count()), x + 1
    
    args = [1]
    launcher = RayLauncher(
        cpu_nbr = 50,
        gpu_nbr = 0,
        func = test_func,
        args = args,
        project_name = "test"
    )
    
    result = launcher()
    print(result)