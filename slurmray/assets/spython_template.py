import ray
import dill
import os
import sys

PROJECT_PATH = {{PROJECT_PATH}}

# Add the project path to the python path
sys.path.append(PROJECT_PATH)

# Start the ray cluster
ray.init({{LOCAL_MODE}})

# Load the function
try:
    # Try loading from source first if available (more robust for version mismatch)
    if os.path.exists(os.path.join(PROJECT_PATH, "func_source.py")) and os.path.exists(os.path.join(PROJECT_PATH, "func_name.txt")):
        import importlib.util
        spec = importlib.util.spec_from_file_location("func_module", os.path.join(PROJECT_PATH, "func_source.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        with open(os.path.join(PROJECT_PATH, "func_name.txt"), "r") as f:
            func_name = f.read().strip()
            
        func = getattr(module, func_name)
        print(f"Loaded function '{func_name}' from source.")
    else:
        raise FileNotFoundError("Source not available")
except Exception as e:
    print(f"Could not load from source: {e}. Fallback to pickle.")
    with open(os.path.join(PROJECT_PATH, "func.pkl"), "rb") as f:
        func = dill.load(f)

# Load the arguments
with open(os.path.join(PROJECT_PATH, "args.pkl"), "rb") as f:
    args = dill.load(f)

# Run the function
result = func(**args)

# Write the result
with open(os.path.join(PROJECT_PATH, "result.pkl"), "wb") as f:
    dill.dump(result, f)
    
# Stop ray
ray.shutdown()
