from slurmray.RayLauncher import RayLauncher

if __name__ == "__main__":

    launcher = RayLauncher(
        project_name="server",
        func=None,
        args=None,
        modules={{MODULES}},
        node_nbr={{NODE_NBR}},
        use_gpu={{USE_GPU}},
        memory={{MEMORY}},
        max_running_time={{MAX_RUNNING_TIME}},
        server_run=False,
        server_ssh=None,
        server_username=None,
    )
    
    # Remove serialization
    launcher.serialize_func_and_args = lambda *args, **kwargs : print("No serialization done.")

    result = launcher()