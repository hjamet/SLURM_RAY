from slurmray.RayLauncher import RayLauncher

# Remove the serialization of the function and arguments
setattr(RayLauncher, "__serialize_func_and_args", lambda *args, **kwargs: None)

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

    result = launcher()