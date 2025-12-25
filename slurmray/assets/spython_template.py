import os
import sys

# Suppress Ray FutureWarning about accelerator visible devices
os.environ.setdefault("RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO", "0")
# Disable uvloop to prevent SIGSEGV in Ray backend (stability fix)
os.environ["RAY_DISABLE_UVLOOP"] = "1"

import ray
import dill

PROJECT_PATH = {{PROJECT_PATH}}

# Add the project path to the python path
sys.path.append(PROJECT_PATH)

# Add editable package source directories to sys.path
# This handles packages uploaded from editable installs (e.g., Poetry projects)
# Check for src/ directory (common Poetry src/ layout)
# For flat layout, PROJECT_PATH is already in sys.path, so packages at root are importable
src_path = os.path.join(PROJECT_PATH, "src")
if os.path.exists(src_path) and os.path.isdir(src_path):
    if src_path not in sys.path:
        sys.path.insert(0, src_path)  # Insert at beginning for priority

# Set GRPC poll strategy to avoid SIGSEGV in some environments
os.environ.setdefault("GRPC_POLL_STRATEGY", "poll")

# Start the ray cluster
ray.init({{LOCAL_MODE}})

# Load the function
# Read the serialization method used
serialization_method = "dill_pickle"  # Default
method_file = os.path.join(PROJECT_PATH, "serialization_method.txt")
if os.path.exists(method_file):
    with open(method_file, "r") as f:
        serialization_method = f.read().strip()

if serialization_method == "source_extraction":
    # Load from source extraction
    try:
        func_source_path = os.path.join(PROJECT_PATH, "func_source.py")
        func_name_path = os.path.join(PROJECT_PATH, "func_name.txt")

        if not os.path.exists(func_source_path) or not os.path.exists(func_name_path):
            raise FileNotFoundError(
                "Source files missing: func_source.py or func_name.txt not found"
            )

        import importlib.util

        spec = importlib.util.spec_from_file_location("func_module", func_source_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with open(func_name_path, "r") as f:
            func_name = f.read().strip()

        func = getattr(module, func_name)
        print(f"Loaded function '{func_name}' from source extraction.")
    except Exception as e:
        print(f"❌ Error loading function from source extraction: {e}")
        print("Falling back to dill pickle...")
        import traceback

        traceback.print_exc()
        with open(os.path.join(PROJECT_PATH, "func.pkl"), "rb") as f:
            func = dill.load(f)
        print("✅ Loaded function from dill pickle (fallback).")
else:
    # Load from dill pickle (default method)
    try:
        func_pickle_path = os.path.join(PROJECT_PATH, "func.pkl")
        if not os.path.exists(func_pickle_path):
            raise FileNotFoundError(f"Pickle file not found: {func_pickle_path}")

        with open(func_pickle_path, "rb") as f:
            func = dill.load(f)
        print(f"✅ Loaded function from dill pickle.")
    except Exception as e:
        print(f"❌ Error loading function from dill pickle: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

# Load the arguments
with open(os.path.join(PROJECT_PATH, "args.pkl"), "rb") as f:
    args = dill.load(f)

# Run the function
try:
    result = func(**args)
except Exception as e:
    print(f"Error executing function: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Write the result
result_path = os.path.join(PROJECT_PATH, "result.pkl")
try:
    with open(result_path, "wb") as f:
        dill.dump(result, f)
    print(f"Result written to {result_path}")
except Exception as e:
    print(f"Error writing result: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Stop ray
try:
    ray.shutdown()
except Exception as e:
    print(f"Warning: Error shutting down Ray: {e}")
