
from slurmray.RayLauncher import RayLauncher
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

    launcher = RayLauncher(
        project_name=project_name,
        func=simple_func,
        args={"x": 10},
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
    
    print(f"Launcher backend type: {type(launcher.backend)}")
    assert "LocalBackend" in str(type(launcher.backend))
    
    result = launcher()
    print(f"Result: {result}")
    
    assert result == 20
    print("✅ Local refactoring test passed!")

if __name__ == "__main__":
    test_local_execution()

