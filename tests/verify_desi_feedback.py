import time
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load env vars explicitly
load_dotenv()

from slurmray import Cluster
from slurmray.cli import DesiManager

# Dummy function to run
def dummy_check(sleep_time=30):
    import time
    print(f"Running dummy job for {sleep_time} seconds...")
    time.sleep(sleep_time)
    return "Done"

def main():
    print("🚀 Starting Verification of Desi Feedback Refactoring")
    
    # 1. Clean up potential legacy mess (optional, but good for clean state)
    # We rely on DesiManager to read the new file.
    mgr = DesiManager()
    print("🔍 Initial Queue State:")
    jobs = mgr.get_jobs()
    print(jobs)
    
    # 2. Launch Job 1 (Consumes resources)
    print("\n🚀 Launching Job 1 (24 CPUs)...")
    launcher1 = Cluster(
        project_name="verification_job_1",
        modules=[],
        node_nbr=1,
        num_gpus=0,
        num_cpus=24, # Takes all CPUs
        memory=16,
        cluster="desi",
        asynchronous=True
    )
    # Run async to not block
    launcher1(func=dummy_check, args={"sleep_time": 60})
    # Wait for it to register (upload takes time)
    print("⏳ Waiting 30s for Job 1 to start and register...")
    time.sleep(30)
    
    print("🔍 Queue State after Job 1 (should be RUNNING):")
    jobs = mgr.get_jobs()
    for j in jobs:
        print(f" - {j['id']} {j['state']} {j.get('cpu')}CPU")
        
    # 3. Launch Job 2 (Should Queue properly now)
    print("\n🚀 Launching Job 2 (Requires 1 CPU, should wait)...")
    launcher2 = Cluster(
        project_name="verification_job_2",
        modules=[],
        node_nbr=1,
        num_gpus=0,
        num_cpus=1, # Needs 1 CPU but Job 1 took 24 (Limit 24)
        memory=4,
        cluster="desi",
        asynchronous=False
    )
    
    # We want to see the output of this one to verify the "Waiting..." message
    # launcher2() blocks and prints output.
    # We'll run it and hopefully see the Waiting message.
    print(">>> Monitoring Job 2 (Expect 'Waiting for resources...' message):")
    try:
        launcher2(func=dummy_check, args={"sleep_time": 10})
    except KeyboardInterrupt:
        print("Interrupted Job 2")

    print("\n✅ Verification script finished.")

if __name__ == "__main__":
    main()
