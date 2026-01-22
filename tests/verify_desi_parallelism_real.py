
import time
import sys
import os
from slurmray import Cluster

def long_task(duration=30):
    import time
    import os
    print(f"Task started on PID {os.getpid()}")
    time.sleep(duration)
    print(f"Task finished on PID {os.getpid()}")
    return f"Done {os.getpid()}"

def main():
    print("🚀 Starting Desi Parallelism Verification (Real Cluster)")
    print("Goal: Launch 5 jobs of 5 CPUs each. Desi has 24 CPUs.")
    print("Expectation: 4 jobs should run immediately (20 CPUs), 5th should wait.")

    jobs = []
    
    # Launch 5 jobs
    for i in range(5):
        print(f"Submitting Job {i+1}/5...")
        launcher = Cluster(
            project_name=f"verify_parallel_{i}",
            cluster="desi",
            num_cpus=5, # 5 * 5 = 25 > 24 CPUs available
            memory=5,
            num_gpus=0,
            asynchronous=True
        )
        job = launcher(long_task, args={"duration": 30})
        jobs.append(job)
        print(f"Job {i+1} submitted with ID: {job.job_id}")
        time.sleep(2) # Slight stagger

    print("\n⏳ Monitoring jobs...")
    
    # Monitor loop
    start_times = {}
    timeout = 120
    start_watch = time.time()
    
    while time.time() - start_watch < timeout:
        active = 0
        waiting = 0
        completed = 0
        
        for i, job in enumerate(jobs):
            # Check logs for "Job started" or "Waiting"
            # This is a bit hacky, normally we'd check status
            # But Desi backend async just gives PID of nohup wrapper
            
            # We can try to infer status from logs
            logs = list(job.logs)
            log_text = "".join(logs)
            
            status = "UNKNOWN"
            if "Resources released" in log_text or "Result received" in log_text:
                status = "COMPLETED"
                completed += 1
            elif "Resources acquired" in log_text or "Job started" in log_text:
                status = "RUNNING"
                if i not in start_times:
                    start_times[i] = time.time()
                active += 1
            elif "Waiting for resources" in log_text:
                status = "WAITING"
                waiting += 1
            elif "Attempting to acquire" in log_text:
                status = "QUEUED"
                waiting += 1
            
            # print(f"Job {i+1}: {status}") 
        
        print(f"Status: Active={active}, Waiting={waiting}, Completed={completed}")
        
        if completed == 5:
            print("✅ All jobs completed.")
            break
            
        if active == 4 and waiting >= 1:
            print("✅ Verified: 4 jobs active, at least 1 waiting. Parallelism limits working!")
            # We can break early if we just want to verify saturation
            # But let's let them finish to be clean
        
        time.sleep(5)

if __name__ == "__main__":
    main()
