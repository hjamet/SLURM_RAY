from slurmray.RayLauncher import RayLauncher

if __name__ == "__main__":
    # Note: This template creates a RayLauncher instance that runs on the cluster.
    # The function execution is handled by spython.py which loads the serialized function.
    # With the refactored API, we don't need to call cluster() here because:
    # 1. The function is already serialized (func_source.py, func.pkl, args.pkl)
    # 2. The actual execution is done via sbatch -> spython.py
    # The RayLauncher instance here is just used to detect cluster mode and submit the job.
    
    cluster = RayLauncher(
        project_name="server",
        modules={{MODULES}},
        node_nbr={{NODE_NBR}},
        use_gpu={{USE_GPU}},
        memory={{MEMORY}},
        max_running_time={{MAX_RUNNING_TIME}},
        server_run=False,
        server_ssh=None,
        server_username=None,
    )
    
    # The job execution is handled by the backend when cluster.run() is called.
    # Since we're on the cluster, the backend will detect cluster=True and submit via sbatch.
    # The actual function execution happens in spython.py.
    # Note: With the refactored API, this would need a dummy function to work.
    # However, this template should be refactored to not need this call at all.
    # For now, we skip execution here as it's handled by the backend infrastructure.
