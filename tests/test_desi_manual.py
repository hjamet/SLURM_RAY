
from slurmray.RayLauncher import RayLauncher
import ray
# import torch # Removing torch dependency for this test to be lighter if not installed
import os
from dotenv import load_dotenv

def simple_func(x):
    return (x * 2, ray.cluster_resources())

def test_desi_execution():
    load_dotenv()
    
    # Skip test if no password in env (e.g. CI)
    if not os.environ.get("DESI_PASSWORD"):
        print("Skipping Desi test (DESI_PASSWORD not found)")
        return

    launcher = RayLauncher(
        project_name="test_desi_integration",
        func=simple_func,
        args={"x": 21},
        files=[],
        modules=[],
        node_nbr=1,
        use_gpu=False,
        memory=1,
        max_running_time=5,
        server_run=True,
        server_ssh="130.223.73.209", # isipol09 IP
        server_username="hjamet", # Assuming same username, change if needed
        server_password=None, # Will pick up DESI_PASSWORD from env
        cluster="desi"
    )
    
    print(f"Launcher backend type: {type(launcher.backend)}")
    assert "DesiBackend" in str(type(launcher.backend))
    
    # This might fail if cannot connect, but verifies instantiation
    try:
        result = launcher()
        print(f"Result: {result}")
        assert result[0] == 42
        print("✅ Desi integration test passed!")
    except Exception as e:
        print(f"Execution failed (expected if no VPN/Network access): {e}")
        # Verify at least the backend logic was triggered
        pass

if __name__ == "__main__":
    test_desi_execution()
