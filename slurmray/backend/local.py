import os
import sys
import time
import subprocess
import dill
from typing import Any

from slurmray.backend.base import ClusterBackend

class LocalBackend(ClusterBackend):
    """Backend for local execution (no scheduler)"""

    def run(self, cancel_old_jobs: bool = True, wait: bool = True) -> Any:
        """Run the job locally"""
        self.logger.info("No cluster detected, running locally...")
        
        self._write_python_script()
        
        # Determine log file path
        # Use job name logic similar to Slurm if possible, or just project name
        job_name = f"{self.launcher.project_name}_local"
        log_path = os.path.join(self.launcher.project_path, f"{job_name}.log")
        
        with open(log_path, "w") as log_file:
            process = subprocess.Popen(
                [sys.executable, os.path.join(self.launcher.project_path, "spython.py")],
                stdout=log_file,
                stderr=subprocess.STDOUT
            )
        
        if not wait:
            self.logger.info(f"Local job started asynchronously. Logs: {log_path} PID: {process.pid}")
            return str(process.pid)

        # Wait for result
        while not os.path.exists(os.path.join(self.launcher.project_path, "result.pkl")):
            time.sleep(0.25)
            # Check if process died
            if process.poll() is not None:
                # Process finished but no result?
                if not os.path.exists(os.path.join(self.launcher.project_path, "result.pkl")):
                    # Check logs
                    with open(log_path, "r") as f:
                        print(f.read())
                    raise RuntimeError("Local process succeeded but no result.pkl found (or failed).")

        with open(os.path.join(self.launcher.project_path, "result.pkl"), "rb") as f:
            result = dill.load(f)

        return result

    def get_result(self, job_id: str) -> Any:
        """Get result from local execution (result.pkl)"""
        # job_id is just project_name descriptor here
        result_path = os.path.join(self.launcher.project_path, "result.pkl")
        if os.path.exists(result_path):
            try:
                with open(result_path, "rb") as f:
                     return dill.load(f)
            except Exception:
                return None
        return None

    def get_logs(self, job_id: str) -> Any:
        """Get logs from local execution"""
        log_path = os.path.join(self.launcher.project_path, f"{job_id}.log")
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                # Yield lines
                for line in f:
                    yield line.strip()
        else:
            yield "Log file not found."

    def cancel(self, job_id: str):
        """Cancel a job (kill local process)"""
        self.logger.info(f"Canceling local job {job_id}...")
        try:
            # Check if job_id looks like a PID (digits)
            if job_id and job_id.isdigit():
                pid = int(job_id)
                self.logger.info(f"Killing process {pid}...")
                os.kill(pid, signal.SIGTERM)
            else:
                # Fallback to pkill by pattern if not a PID (old behavior or synchronous fallback)
                cmd = ["pkill", "-f", f"{self.launcher.project_path}/spython.py"]
                subprocess.run(cmd, check=False)
            
            self.logger.info("Local process killed.")
        except Exception as e:
            self.logger.warning(f"Failed to kill local process: {e}")

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
        # Local mode doesn't need special address usually, or 'auto' is fine.
        # Original code:
        # if self.cluster or self.server_run:
        #    local_mode = ...
        # else:
        #    local_mode = "" (empty)
        
        local_mode = ""
        text = text.replace(
            "{{LOCAL_MODE}}",
            local_mode,
        )
        with open(os.path.join(self.launcher.project_path, "spython.py"), "w") as f:
            f.write(text)

