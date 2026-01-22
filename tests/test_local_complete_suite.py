
import pytest
import os
import time
import sys
from slurmray import Cluster

# --- Helper Functions (Tasks) ---

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
    raise ValueError("Expected local failure")

def gpu_task():
    import torch
    return torch.cuda.is_available()

def concurrency_task(duration):
    import time
    time.sleep(duration)
    return "Done"

# --- Tests ---

def test_local_cpu_execution():
    """Verify basic CPU execution in local mode."""
    launcher = Cluster(
        project_name="test_local_cpu",
        cluster="local",
        num_cpus=1,
        num_gpus=0,
        node_nbr=1,
        max_running_time=5
    )
    result = launcher(cpu_task, args={"x": 5})
    assert result == 25

def test_local_return_values():
    """Verify complex return value serialization/deserialization in local mode."""
    launcher = Cluster(
        project_name="test_local_return",
        cluster="local",
        num_cpus=1,
        num_gpus=0
    )
    result = launcher(complex_return_task)
    assert isinstance(result, dict)
    assert result["list"] == [1, 2, 3]
    assert result["tuple"] == (4, 5)
    assert result["dict"] == {"a": 1}
    assert result["none"] is None
    assert result["bool"] is True
    assert result["float"] == 3.14

def test_local_error_propagation():
    """Verify that exceptions are propagated (or reported) locally."""
    launcher = Cluster(
        project_name="test_local_error",
        cluster="local",
        num_cpus=1
    )
    
    # LocalBackend currently raises RuntimeError if the process fails or no result.pkl
    # We expect it to verify that the local process failed.
    # Note: The subprocess prints the traceback to the log file (and stdout via generic backend logic).
    with pytest.raises(RuntimeError) as excinfo:
        launcher(failing_task)
    
    assert "Local process succeeded but no result.pkl found" in str(excinfo.value)

def test_local_gpu_execution():
    """Verify GPU execution (use_gpu implied by num_gpus > 0)."""
    # This should run even if no GPU is present (processed by LocalBackend),
    # but torch.cuda.is_available() will return False.
    launcher = Cluster(
        project_name="test_local_gpu",
        cluster="local",
        num_cpus=1,
        num_gpus=1
    )
    
    result = launcher(gpu_task)
    assert isinstance(result, bool)

def test_local_concurrency():
    """Verify concurrent job submission and execution in local mode."""
    # Launch 3 jobs that take 2 seconds each
    
    launchers = []
    job_count = 3
    
    print("\nSubmitting concurrent local jobs...")
    for i in range(job_count):
        launcher = Cluster(
            project_name=f"test_local_conc_{i}",
            cluster="local",
            num_cpus=1,
            num_gpus=0,
            asynchronous=True 
        )
        # In async mode, this returns a FunctionReturn object
        job = launcher(concurrency_task, args={"duration": 2})
        launchers.append(job)
        time.sleep(0.5)
    
    # Wait for all jobs to complete
    completed_jobs = 0
    start_time = time.time()
    timeout = 60
    
    while completed_jobs < job_count and (time.time() - start_time) < timeout:
        active_count = 0
        completed_jobs = 0
        
        for job in launchers:
            res = job.result
            if res != "Compute still in progress":
                completed_jobs += 1
                assert res == "Done"
            else:
                active_count += 1
        
        if completed_jobs == job_count:
            break
            
        time.sleep(1)
        print(f"Waiting for jobs: {completed_jobs}/{job_count} completed. Active: {active_count}")
    
    assert completed_jobs == job_count, f"Not all jobs completed within {timeout}s"
