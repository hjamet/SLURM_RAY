from abc import ABC, abstractmethod
from typing import Any, Dict

class ClusterBackend(ABC):
    """Abstract base class for cluster backends"""

    def __init__(self, launcher):
        """
        Initialize the backend.
        
        Args:
            launcher: The RayLauncher instance containing configuration
        """
        self.launcher = launcher
        self.logger = launcher.logger

    @abstractmethod
    def run(self, cancel_old_jobs: bool = True) -> Any:
        """
        Run the job on the backend.
        
        Args:
            cancel_old_jobs (bool): Whether to cancel old jobs before running
            
        Returns:
            Any: The result of the execution
        """
        pass

    @abstractmethod
    def cancel(self, job_id: str):
        """
        Cancel a running job.
        
        Args:
            job_id (str): The ID of the job to cancel
        """
        pass

