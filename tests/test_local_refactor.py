
from slurmray import Cluster
import ray
import os
import shutil

def simple_func(x):
    return x * 2

def test_local_execution():
    project_name = "test_local_refactor"
    # Cleanup previous run
    if os.path.exists(f".slogs/{project_name}"):
        shutil.rmtree(f".slogs/{project_name}")

    cluster = Cluster(
        project_name=project_name,
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
    
    print(f"Cluster backend type: {type(cluster.backend)}")
    assert "LocalBackend" in str(type(cluster.backend))
    
    result = cluster(simple_func, args={"x": 10})
    print(f"Result: {result}")
    
    assert result == 20
    print("✅ Local refactoring test passed!")

if __name__ == "__main__":
    test_local_execution()

