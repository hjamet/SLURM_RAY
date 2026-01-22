
import time
import os
import sys
import dill
from slurmray import Cluster

# Define a function to be executed asynchronously
def long_task(x):
    import time
    print(f"Starting task with input {x}...")
    for i in range(5):
        print(f"Step {i}")
        time.sleep(1) # Simulate work
    print("Task finished!")
    return x * 2

def verify_async():
    print("Initializing RayLauncher with asynchronous=True...")
    # Initialize launcher in local mode for testing
    # Note: 'local' mode in RayLauncher usually means running locally but still using the wrapper structure.
    # We might need to handle 'local' mode carefully if it just uses subprocess.
    launcher = Cluster(
        project_name="async_test_repro",
        asynchronous=True,
        cluster="local",
        retention_days=1,
        files=[]
    )

    print("Launching task...")
    start_time = time.time()
    # This should return immediately
    function_return = launcher(long_task, args={"x": 21})
    end_time = time.time()
    
    print(f"Launch took {end_time - start_time:.4f} seconds")
    
    # Check if we got a FunctionReturn object (checking by attribute presence essentially)
    if not hasattr(function_return, 'logs') or not hasattr(function_return, 'result'):
        print(f"FAILED: Returned object {function_return} does not have expected attributes 'logs' and 'result'")
        return

    print("Identified FunctionReturn object.")
    
    # Check initial status
    print(f"Initial Result: {function_return.result}")
    
    # Pickle the object to simulate saving state
    with open("func_ret.pkl", "wb") as f:
        dill.dump(function_return, f)
    print("Saved FunctionReturn object to func_ret.pkl")

    # Simulate "restart" / independent monitoring
    print("Simulating restart (loading object)...")
    with open("func_ret.pkl", "rb") as f:
        loaded_ret = dill.load(f)
    
    print("Monitoring execution...")
    # Wait for completion
    timeout = 30
    start_wait = time.time()
    
    # Basic polling loop using the loaded object
    while str(loaded_ret.result) == "Compute still in progress" and (time.time() - start_wait < timeout):
        # Consume logs
        # Note: Depending on implementation, logs might be a generator or list. 
        # If it's a generator, we iterate. If list, we print new items.
        # Implementation Detail: logs attribute is supposed to be usable.
        # Let's assume it provides checking capability or we just print the result check.
        time.sleep(1)
        print(f"Waiting... Status: {loaded_ret.result}")
        
    print(f"Final Result: {loaded_ret.result}")
    
    # Verify result
    if loaded_ret.result == 42:
        print("SUCCESS: Result is correct (42)")
    else:
        print(f"FAILURE: Result is incorrect: {loaded_ret.result}")

    # Clean up
    if os.path.exists("func_ret.pkl"):
        os.remove("func_ret.pkl")

if __name__ == "__main__":
    verify_async()
