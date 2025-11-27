import os
import sys
import time
import subprocess
import dill
from typing import Any

from slurmray.backend.base import ClusterBackend

class LocalBackend(ClusterBackend):
    """Backend for local execution (no scheduler)"""

    def run(self, cancel_old_jobs: bool = True) -> Any:
        """Run the job locally"""
        self.logger.info("No cluster detected, running locally...")
        
        self._write_python_script()
        
        subprocess.Popen(
            [sys.executable, os.path.join(self.launcher.project_path, "spython.py")]
        )

        # Load the result
        while not os.path.exists(os.path.join(self.launcher.project_path, "result.pkl")):
            time.sleep(0.25)
        with open(os.path.join(self.launcher.project_path, "result.pkl"), "rb") as f:
            result = dill.load(f)

        return result

    def cancel(self, job_id: str):
        """Cancel a job (not applicable for local synchronous execution usually, but could kill process)"""
        # In local mode, we launched with Popen but didn't keep the process handle easily accessible in this architecture yet.
        # For now, do nothing or log warning.
        self.logger.warning("Cancel not fully implemented for LocalBackend (process handle not stored)")
        pass

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

