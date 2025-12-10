import os
import sys
import shutil
import tempfile
from slurmray.RayLauncher import RayLauncher

# Create a temporary directory for the project
temp_dir = tempfile.mkdtemp()
project_dir = os.path.join(temp_dir, "test_project")
os.makedirs(project_dir)

# Create src layout
src_dir = os.path.join(project_dir, "src")
pkg_dir = os.path.join(src_dir, "test_pkg")
os.makedirs(pkg_dir)

# Create __init__.py
with open(os.path.join(pkg_dir, "__init__.py"), "w") as f:
    f.write("def hello(): return 'hello'")

# Create main script
main_script = os.path.join(project_dir, "main.py")
with open(main_script, "w") as f:
    f.write("""
from test_pkg import hello

def my_func():
    return hello()
""")

# Setup RayLauncher
# We need to change cwd to the project directory for RayLauncher to work properly
cwd = os.getcwd()
os.chdir(project_dir)

# Add src to sys.path so we can import test_pkg locally (needed for scanner)
sys.path.insert(0, src_dir)
# Add project dir to sys.path to import main
sys.path.insert(0, project_dir)

try:
    print(f"Project created at {project_dir}")
    print(f"Layout: {os.listdir(project_dir)}")
    print(f"Src: {os.listdir(src_dir)}")
    
    # Import the function from main.py so inspect.getfile returns a file inside project_dir
    import importlib.util
    spec = importlib.util.spec_from_file_location("main", main_script)
    main_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_module)
    task_func = main_module.my_func
    
    launcher = RayLauncher(
        project_name="test_repro",
        cluster="local", # Use local to avoid actual connection, we just want to check detection
        files=[] # Empty initially
    )
    
    # Let's call the scanner directly first to see if it detects it
    from slurmray.scanner import ProjectScanner
    scanner = ProjectScanner(project_dir)
    deps = scanner.detect_dependencies_from_function(task_func)
    
    print(f"Detected dependencies: {deps}")
    
    expected_dep_unix = "src/test_pkg"
    expected_dep_unix_alt = "src/test_pkg/"
    expected_dep_win = os.path.join("src", "test_pkg")
    
    if any(d.startswith(expected_dep_unix) for d in deps) or expected_dep_win in deps:
        print("SUCCESS: src/test_pkg detected")
    else:
        print("FAILURE: src/test_pkg NOT detected")
        
    # Verify SlurmBackend has _sync_local_files_incremental
    from slurmray.backend.slurm import SlurmBackend
    if hasattr(SlurmBackend, "_sync_local_files_incremental"):
        print("SUCCESS: SlurmBackend has _sync_local_files_incremental")
    else:
        print("FAILURE: SlurmBackend MISSING _sync_local_files_incremental")
        
finally:
    # Cleanup
    sys.path.pop(0)
    os.chdir(cwd)
    shutil.rmtree(temp_dir)
