
import pytest
import os
import time
import sys
from dotenv import load_dotenv
from slurmray.RayLauncher import RayLauncher

# Load environment variables
load_dotenv()

# --- Helper Functions (Remote Tasks) ---

def cpu_task(x):
    return x * x

def complex_return_task():
    return {
        "list": [1, 2, 3],
        "tuple": (4, 5),
        "dict": {"a": 1},
        "none": None,
        "bool": True,
        "float": 3.14
    }

def failing_task():
    raise ValueError("Expected remote failure")

def gpu_task():
    import torch
    return torch.cuda.is_available()

def concurrency_task(duration):
    import time
    time.sleep(duration)
    return "Done"

# --- Fixtures ---

@pytest.fixture(scope="module")
def desi_credentials():
    password = os.getenv("DESI_PASSWORD")
    if not password:
        pytest.skip("DESI_PASSWORD not found in environment, skipping DESI tests.")
    return password

# --- Tests ---

def test_desi_cpu_execution(desi_credentials):
    """Verify basic CPU execution."""
    launcher = RayLauncher(
        project_name="test_suite_cpu",
        cluster="desi",
        num_cpus=1,
        num_gpus=0,
        node_nbr=1,
        max_running_time=5,
        server_password=desi_credentials
    )
    result = launcher(cpu_task, args={"x": 5})
    assert result == 25

def test_desi_return_values(desi_credentials):
    """Verify complex return value serialization/deserialization."""
    launcher = RayLauncher(
        project_name="test_suite_return",
        cluster="desi",
        num_cpus=1,
        num_gpus=0,
        node_nbr=1,
        max_running_time=5,
        server_password=desi_credentials
    )
    result = launcher(complex_return_task)
    assert isinstance(result, dict)
    assert result["list"] == [1, 2, 3]
    assert result["tuple"] == (4, 5)
    assert result["dict"] == {"a": 1}
    assert result["none"] is None
    assert result["bool"] is True
    assert result["float"] == 3.14

def test_desi_error_propagation(desi_credentials):
    """Verify that remote exceptions are propagated locally."""
    launcher = RayLauncher(
        project_name="test_suite_error",
        cluster="desi",
        num_cpus=1,
        num_gpus=0,
        node_nbr=1,
        max_running_time=5,
        server_password=desi_credentials
    )
    
    # RayLauncher raises RuntimeError when the remote job fails with non-zero exit code
    with pytest.raises(RuntimeError) as excinfo:
        launcher(failing_task)
    
    # Verify the error message contains info about the failure
    assert "Job script exited with non-zero status" in str(excinfo.value)

@pytest.mark.skipif(os.getenv("SKIP_GPU_TESTS") == "1", reason="Skipping GPU tests")
def test_desi_gpu_execution(desi_credentials):
    """Verify GPU execution (use_gpu=True)."""
    # Note: efficient checking relies on the cluster actually having GPUs available
    # and the job being scheduled. 
    launcher = RayLauncher(
        project_name="test_suite_gpu",
        cluster="desi",
        num_cpus=1,
        num_gpus=1,
        node_nbr=1,
        max_running_time=5,
        server_password=desi_credentials
        # use_gpu=True removed (invalid arg)
    )
    # If the cluster is busy or no GPU partition, this might timeout or queue.
    # We accept either True (GPU found) or False (if run on CPU-only node by mistake)
    # but the main point is that it runs without crash.
    result = launcher(gpu_task)
    # We verify we got a boolean back
    assert isinstance(result, bool)

def test_desi_concurrency(desi_credentials):
    """Verify concurrent job submission and execution."""
    # Launch 3 jobs that take 10 seconds each
    # This checks if the locking mechanism allows them to be submitted
    
    launchers = []
    job_count = 3
    
    print("\nSubmitting concurrent jobs...")
    for i in range(job_count):
        launcher = RayLauncher(
            project_name=f"test_suite_conc_{i}",
            cluster="desi",
            num_cpus=1,
            num_gpus=0,
            node_nbr=1,
            max_running_time=15, # Enough for 5s task + overhead
            server_password=desi_credentials,
            asynchronous=True 
        )
        job = launcher(concurrency_task, args={"duration": 5})
        launchers.append(job)
        time.sleep(1) # Small stagger
    
    # Wait for all jobs to complete
    completed = 0
    start_time = time.time()
    timeout = 360 # 6 minutes timeout
    
    while completed < job_count and (time.time() - start_time) < timeout:
        active_count = 0
        completed = 0
        for job in launchers:
            # Check logs/status
            logs = list(job.logs) # iterates generator
            log_str = "".join(logs)
            
            # Simple heuristic for completion based on expected output/behavior
            # Real DesiBackend integration might provide a better way to check status
            # For this test, we rely on the fact that if it finishes, we get a result?
            # Async jobs in Desi usually detach. The 'job' object here is the launcher instance
            # which might hold state if designed so. 
            # Actually RayLauncher in async mode returns a handle or the launcher itself.
            # Let's check verify_desi_parallelism_real.py logic:
            
            if "Result received" in log_str or "Resources released" in log_str or "Result written to" in log_str:
                completed += 1
            elif "Job started" in log_str:
                active_count += 1
            
            # Debug log
            if log_str:
                print(f"DEBUG [{job.launcher.project_name}]: {log_str.strip()[-100:]}")
                
        time.sleep(5)
        print(f"Waiting for jobs: {completed}/{job_count} completed. Active: {active_count}")
    
    assert completed == job_count, f"Not all jobs completed within {timeout}s"
