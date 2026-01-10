
import os
import sys
import time
import fcntl
import subprocess
import json
import random

# Configuration
LOCK_FILE = "/tmp/slurmray_desi_resources.lock"
STATE_FILE = "/tmp/slurmray_desi_resources.json"

# Hardware Limits (Desi specific or Injected)
LIMITS = {
    "cpu": {{LIMIT_CPU}},
    "ram": {{LIMIT_RAM}}, # GB
    "gpu": {{LIMIT_GPU_IDS}} # List of GPU IDs
}

# Job Requirements (Injected)
REQ_CPU = {{REQ_CPU}}
REQ_RAM = {{REQ_RAM}}
REQ_GPU = {{REQ_GPU}}
JOB_NAME = "{{JOB_NAME}}"
USER_NAME = "{{USER_NAME}}"
PROJECT_DIR = "{{PROJECT_DIR}}"

MAX_RETRIES = 100000 # Effectively infinite
RETRY_DELAY = 10 # Check every 10 seconds

def get_lock(fd):
    '''Acquire exclusive lock on state file'''
    fcntl.lockf(fd, fcntl.LOCK_EX)

def release_lock(fd):
    '''Release lock'''
    fcntl.lockf(fd, fcntl.LOCK_UN)

def load_state():
    '''Load state from JSON file'''
    if not os.path.exists(STATE_FILE):
        return {"jobs": []}
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"jobs": []}

def save_state(state):
    '''Save state to JSON file'''
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def is_pid_running(pid):
    '''Check if PID is running using /proc'''
    try:
        return os.path.exists(f"/proc/{pid}")
    except Exception:
        return False

def clean_stale_jobs(state):
    '''Remove jobs that are no longer running'''
    active_jobs = []
    dirty = False
    for job in state.get("jobs", []):
        pid = job["pid"]
        status = job.get("status", "running")
        
        # Always check PID existence for running jobs
        # For waiting jobs, the process should also be alive (it's this script waiting)
        if is_pid_running(pid):
            active_jobs.append(job)
        else:
            # print(f"🧹 Cleaning stale job {pid} from registry")
            dirty = True
            
    state["jobs"] = active_jobs
    return state, dirty

def get_resource_usage(state):
    '''Calculate current resource usage'''
    used_cpu = 0
    used_ram = 0
    used_gpus = []
    
    # Only count RUNNING jobs for resource usage
    for job in state["jobs"]:
        if job.get("status") == "running":
            used_cpu += job["cpu"]
            used_ram += job["ram"]
            used_gpus.extend(job["gpu_ids"])
            
    return used_cpu, used_ram, used_gpus

def check_resources(state):
    '''Check if resources are available'''
    used_cpu, used_ram, used_gpus = get_resource_usage(state)
    
    available_cpu = LIMITS["cpu"] - used_cpu
    available_ram = LIMITS["ram"] - used_ram
    available_gpus = [g for g in LIMITS["gpu"] if g not in used_gpus]
    
    # Resource Summary String
    gpu_total = len(LIMITS["gpu"])
    gpu_used_count = len(used_gpus)
    summary = f"Used: CPU {used_cpu}/{LIMITS['cpu']}, RAM {used_ram}/{LIMITS['ram']} GB, GPU {gpu_used_count}/{gpu_total}"

    if REQ_CPU > LIMITS["cpu"]:
         return False, None, f"Global Fail: Requested CPU ({REQ_CPU}) > Limit ({LIMITS['cpu']})"
    if REQ_RAM > LIMITS["ram"]:
         return False, None, f"Global Fail: Requested RAM ({REQ_RAM}) > Limit ({LIMITS['ram']})"
    if REQ_GPU > len(LIMITS["gpu"]):
         return False, None, f"Global Fail: Requested GPU ({REQ_GPU}) > Limit ({len(LIMITS['gpu'])})"

    if REQ_CPU > available_cpu:
        return False, None, f"Not enough CPU. ({summary})"
        
    if REQ_RAM > available_ram:
        return False, None, f"Not enough RAM. ({summary})"
        
    if REQ_GPU > 0:
        if len(available_gpus) < REQ_GPU:
            return False, None, f"Not enough GPU. ({summary})"
        # Allocate specific GPUs
        allocated_gpus = available_gpus[:REQ_GPU]
        return True, allocated_gpus, "OK"
    
    return True, [], "OK"

def update_myself_in_state(state, status, gpu_ids=[]):
    '''Update or add my own entry in the state'''
    my_pid = os.getpid()
    
    # Check if I exist
    existing = next((j for j in state["jobs"] if j["pid"] == my_pid), None)
    
    entry = {
        "pid": my_pid,
        "user": USER_NAME,
        "func_name": JOB_NAME, # Used as 'name' in CLI
        "project_dir": PROJECT_DIR,
        "cpu": REQ_CPU,
        "ram": REQ_RAM,
        "gpu_ids": gpu_ids,
        "req_gpu": REQ_GPU,
        "status": status,
        "timestamp": existing["timestamp"] if existing else time.time()
    }
    
    if existing:
        # Update in place
        for i, job in enumerate(state["jobs"]):
            if job["pid"] == my_pid:
                state["jobs"][i] = entry
                break
    else:
        # Append
        state["jobs"].append(entry)
        
    return state

def get_queue_position(state):
    '''Get my position in the waiting queue'''
    my_pid = os.getpid()
    waiting_jobs = [j for j in state["jobs"] if j.get("status") == "waiting"]
    waiting_jobs.sort(key=lambda x: x["timestamp"])
    
    for i, job in enumerate(waiting_jobs):
        if job["pid"] == my_pid:
            return i + 1, len(waiting_jobs)
    return None, len(waiting_jobs)

def format_duration(seconds):
    '''Format duration in H:M:S'''
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def print_status_table(state, my_pos, total_waiting, used_cpu, used_ram, used_gpus):
    '''Print a nice ASCII table of the current state'''
    
    my_pid = os.getpid()
    jobs = state["jobs"]
    
    # Sort waiting by timestamp
    waiting = sorted([j for j in jobs if j["status"] == "waiting"], key=lambda x: x["timestamp"])
    
    # Calculate what is taken by Running jobs
    taken_cpu = used_cpu
    taken_ram = used_ram
    taken_gpu = len(used_gpus)
    
    # Add waiting jobs ahead of me
    for job in waiting:
        if job["pid"] == my_pid:
            break
        taken_cpu += job["cpu"]
        taken_ram += job["ram"]
        # Use req_gpu if available, else fallback (Desi usually small scale so default 0 safe-ish but we added tracking)
        taken_gpu += job.get("req_gpu", 0) 
        
    avail_cpu_me = max(0, LIMITS["cpu"] - taken_cpu)
    avail_ram_me = max(0, LIMITS["ram"] - taken_ram)
    avail_gpu_me = max(0, len(LIMITS["gpu"]) - taken_gpu)
    
    # Header
    print(f"\n⏳ Job is queued (Position #{my_pos}/{total_waiting}).", flush=True)
    print(f"   Limits:             CPU {LIMITS['cpu']},    RAM {LIMITS['ram']}GB,    GPU {len(LIMITS['gpu'])}", flush=True)
    print(f"   Available for me:   CPU {avail_cpu_me}/{REQ_CPU},  RAM {avail_ram_me}/{REQ_RAM}GB,   GPU {avail_gpu_me}/{REQ_GPU}", flush=True)
    
    headers = ["PID", "User", "State", "Start Time", "Duration", "CPU", "RAM", "GPU"]
    fmt = "{:<8} {:<12} {:<12} {:<10} {:<10} {:>3} {:>5} {:>3}"
    
    print("-" * 75, flush=True)
    print(fmt.format(*headers), flush=True)
    print("-" * 75, flush=True)
    
    # Sort: Runnning first, then Waiting (by timestamp)
    running = sorted([j for j in jobs if j["status"] == "running"], key=lambda x: x["timestamp"])
    
    now = time.time()
    
    for i, job in enumerate(running + waiting):
        pid_str = str(job["pid"])
        user_str = job["user"][:12]
        
        status_str = job["status"].upper()
        if job["status"] == "waiting":
            # Find position
            sub_idx = next((idx for idx, j in enumerate(waiting) if j["pid"] == job["pid"]), -1)
            status_str = f"WAIT #{sub_idx + 1}"
            
        start_time_str = time.strftime('%H:%M:%S', time.localtime(job["timestamp"]))
        duration_str = format_duration(now - job["timestamp"])
        
        cpu_str = str(job["cpu"])
        ram_str = f"{job['ram']}G"
        
    # Display allocated for running, requested for waiting
        if job["status"] == "running":
             gpu_count = len(job["gpu_ids"])
             gpu_display = f"{gpu_count}/{len(LIMITS['gpu'])}"
        else:
             gpu_count = job.get("req_gpu", 0)
             gpu_display = f"{gpu_count}/{len(LIMITS['gpu'])}"
        
        # Highlight my own job
        line = fmt.format(pid_str, user_str, status_str, start_time_str, duration_str, cpu_str, ram_str, gpu_display)
        if job["pid"] == os.getpid():
            print(f"➤ {line}", flush=True)
        else:
            print(f"  {line}", flush=True)

    print("-" * 75 + "\n", flush=True)


def main():
    print(f"🔒 Requesting resources: {REQ_CPU} CPU, {REQ_RAM} GB RAM, {REQ_GPU} GPU", flush=True)
    
    # Ensure lock file exists
    if not os.path.exists(LOCK_FILE):
        try:
            open(LOCK_FILE, 'w').close()
            os.chmod(LOCK_FILE, 0o666) # Try to make it writable for all
        except IOError:
            pass # Maybe registered by another user
        
    try:
        lock_fd = open(LOCK_FILE, 'w')
    except IOError as e:
        print(f"❌ Could not open lock file {LOCK_FILE}: {e}")
        # Build robustness: fall back to a user-local lock file? 
        # No, for global resource management we need a shared file.
        # Assuming permissions are set correctly on the server (/tmp is usually rwxrwxrwt).
        sys.exit(1)
    
    allocated_gpu_ids = []
    registered_as_waiting = False
    last_reason_msg = ""
    
    # Initial registration as WAITING
    get_lock(lock_fd)
    try:
        state = load_state()
        state, dirty = clean_stale_jobs(state)
        # Check immediately (Fast Path)
        allowed, gpus, reason = check_resources(state)
        
        if allowed:
            # Direct start
            state = update_myself_in_state(state, "running", gpus)
            save_state(state)
            allocated_gpu_ids = gpus
            print(f"✅ Resources acquired immediately! (PID {os.getpid()}). CPU: {REQ_CPU}, RAM: {REQ_RAM}GB, GPUs: {REQ_GPU}", flush=True)
            run_job = True
        else:
            if "Global Fail" in reason:
                print(f"❌ {reason}")
                run_job = False # Should exit
            else:
                # Register as waiting
                state = update_myself_in_state(state, "waiting", [])
                save_state(state)
                registered_as_waiting = True
                run_job = False # Enter loop
                print(f"⏳ Resources busy. Added to queue. Reason: {reason}", flush=True)
    finally:
        release_lock(lock_fd)

    if "Global Fail" in reason and not allocated_gpu_ids:
         sys.exit(1)

    # Retry Loop if not started immediately
    if not run_job and registered_as_waiting:
        for attempt in range(MAX_RETRIES):
            time.sleep(RETRY_DELAY)
            
            get_lock(lock_fd)
            try:
                state = load_state()
                state, dirty = clean_stale_jobs(state)
                
                # Check resources again
                allowed, gpus, reason = check_resources(state)
                
                if allowed:
                    # Switch to RUNNING
                    state = update_myself_in_state(state, "running", gpus)
                    save_state(state)
                    allocated_gpu_ids = gpus
                    print(f"✅ Resources acquired! (PID {os.getpid()}). CPU: {REQ_CPU}, RAM: {REQ_RAM}GB, GPUs: {len(gpus)}/{REQ_GPU}", flush=True)
                    break
                else:
                    # Refresh my timestamp/status (keep alive)
                    state = update_myself_in_state(state, "waiting", [])
                    save_state(state)
                    
                    # Display Status Update
                    pos, total = get_queue_position(state)
                    used_cpu, used_ram, used_gpus = get_resource_usage(state)
                    gpu_total = len(LIMITS["gpu"])
                    gpu_used = len(used_gpus)
                    
                    # Get list of running jobs for context (who is blocking?)
                    running_jobs_desc = []
                    for job in state["jobs"]:
                         if job["status"] == "running":
                             running_jobs_desc.append(f"{job['user']}({job['cpu']}C)")
                    
                    running_users = ", ".join(running_jobs_desc)
                    if not running_users:
                        running_users = "None"

                    # Construct message
                    msg = f"⏳ Queue: #{pos}/{total} (Active: {running_users})."
                    res_summary = f"[{used_cpu}/{LIMITS['cpu']} CPU, {used_ram}/{LIMITS['ram']} RAM, {gpu_used}/{gpu_total} GPU]"
                    
                    full_msg = f"{msg} {res_summary}"
                    
                    # Only print if message changed or every 60s (every 6 attempts)
                    # Only print if message changed or every 60s (every 6 attempts)
                    # We accept slightly more spam for the table to ensure visibility of updates
                    current_table_hash = hash(json.dumps(state['jobs'], sort_keys=True))
                    
                    if current_table_hash != last_reason_msg or attempt % 6 == 0:
                         print_status_table(state, pos, total, used_cpu, used_ram, used_gpus)
                         last_reason_msg = current_table_hash
                        
            finally:
                release_lock(lock_fd)
    
    # Set CUDA_VISIBLE_DEVICES if validated
    if allocated_gpu_ids:
        os.environ["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, allocated_gpu_ids))
        print(f"🔧 Set CUDA_VISIBLE_DEVICES={os.environ['CUDA_VISIBLE_DEVICES']}", flush=True)
    elif REQ_GPU == 0:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    # Execute Runtime
    venv_python = os.path.join(os.path.dirname(__file__), "venv", "bin", "python")
    if os.path.exists(venv_python):
        python_cmd = venv_python
    else:
        python_cmd = sys.executable

    try:
        # Run the actual workload
        process = subprocess.Popen(
            [python_cmd, "-u", "spython.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        for line in process.stdout:
            print(line, end='', flush=True)
            
        process.wait()
        
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, process.args)

    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except Exception as e:
        print(f"❌ Job failed: {e}", flush=True)
        sys.exit(1)
    finally:
        # Cleanup
        # print("🧹 Cleaning up resource registration...", flush=True) 
        # (Be silent on cleanup to avoid log spam at end)
        try:
            get_lock(lock_fd)
            try:
                state = load_state()
                # Remove my PID
                my_pid = os.getpid()
                state["jobs"] = [j for j in state["jobs"] if j["pid"] != my_pid]
                save_state(state)
                # print("✅ Resources released.", flush=True)
            finally:
                release_lock(lock_fd)
                lock_fd.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
