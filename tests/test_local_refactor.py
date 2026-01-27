
from slurmray import Cluster
import ray
import os
import shutil

def simple_func(x):
    return x * 2

def test_local_execution():
    cluster = Cluster(
        # project_name="test_local_refactor", # Removed to test auto-detection
        files=[],
        modules=[],
        node_nbr=1,
        use_gpu=False,
        memory=1,
        max_running_time=1,
        server_run=False, # FORCE LOCAL EXECUTION
        server_ssh="localhost",
        server_username="user",
        server_password="password",
    )
    
    # Check if auto-detection worked (should be git root 'SLURM_RAY' or cwd)
    print(f"Detected project name: {cluster.project_name}")
    
    # Cleanup previous run (now using the detected name)
    if os.path.exists(f".slogs/{cluster.project_name}"):
        shutil.rmtree(f".slogs/{cluster.project_name}")
    
    print(f"Cluster backend type: {type(cluster.backend)}")
    assert "LocalBackend" in str(type(cluster.backend))
    
    result = cluster(simple_func, args={"x": 10})
    print(f"Result: {result}")
    
    assert result == 20
    print("✅ Local refactoring test passed!")

if __name__ == "__main__":
    test_local_execution()

