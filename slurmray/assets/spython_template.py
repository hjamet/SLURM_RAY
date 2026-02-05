# ============================================================================
# MULTIPROCESSING FIX - MUST BE FIRST BEFORE ANY OTHER IMPORTS
# ============================================================================
# On Python 3.11+ Linux, the default multiprocessing start method is 'spawn'.
# The 'spawn' method requires `if __name__ == '__main__':` guard, which doesn't
# exist in SlurmRay's dill-deserialized execution context.
#
# This fix sets the default start method to 'fork', which works for most cases
# (FlagEmbedding, torch.DataLoader with num_workers, etc.)
#
# KNOWN LIMITATION: Libraries that explicitly call `mp.get_context("spawn")`
# (e.g., sentence-transformers.start_multi_process_pool()) will still use spawn.
# This cannot be monkey-patched because fork+CUDA causes:
# "RuntimeError: Cannot re-initialize CUDA in forked subprocess"
# Workaround: Use sequential encoding or ensure CUDA is not initialized before fork.
# ============================================================================
import multiprocessing
import platform

if platform.system() == "Linux":
    try:
        multiprocessing.set_start_method("fork", force=True)
    except RuntimeError:
        pass  # Already set

# Now safe to import everything else
import os
import sys

# Environment variables for ML libraries that respect them
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")  # Hugging Face tokenizers
os.environ.setdefault("OMP_NUM_THREADS", "1")  # OpenMP threading

# Suppress Ray FutureWarning about accelerator visible devices
os.environ.setdefault("RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO", "0")
# Disable uvloop to prevent SIGSEGV in Ray backend (stability fix)
os.environ["RAY_DISABLE_UVLOOP"] = "1"

import ray
import dill

PROJECT_PATH = {{PROJECT_PATH}}

# Add the project path to the python path
sys.path.insert(0, PROJECT_PATH)

# Add editable package source directories to sys.path
# This handles packages uploaded from editable installs (e.g., Poetry projects)
# Check for src/ directory (common Poetry src/ layout)
# For flat layout, PROJECT_PATH is already in sys.path, so packages at root are importable
src_path = os.path.join(PROJECT_PATH, "src")
if os.path.exists(src_path) and os.path.isdir(src_path):
    if src_path not in sys.path:
        sys.path.insert(0, src_path)  # Insert at beginning for priority

# Pre-import the root package to help dill find the module
{{PRE_IMPORT}}

# Set GRPC poll strategy to avoid SIGSEGV in some environments
os.environ.setdefault("GRPC_POLL_STRATEGY", "poll")


# Start the ray cluster
try:
    ray.init({{LOCAL_MODE}})
except Exception as e:
    print(f"❌ Ray initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    sys.exit(1)

# ============================================================================
# RAY MULTIPROCESSING PATCH - PROXY MODULE APPROACH (v9.0.2)
# ============================================================================
# Instead of replacing multiprocessing entirely with ray.util.multiprocessing
# (which only exposes Pool, JoinableQueue, TimeoutError), we create a proxy
# module that inherits ALL attributes from the original multiprocessing but
# overrides only Pool with Ray's distributed version.
#
# This fixes ImportError for Queue, Process, Lock, etc. from libraries like
# sentence-transformers, torch.multiprocessing.reductions, and others.
# ============================================================================
print("🔄 SlurmRay: Patching multiprocessing.Pool with Ray (proxy module)...")

# Import the original multiprocessing BEFORE we patch sys.modules
import multiprocessing as _original_mp
from ray.util import multiprocessing as ray_mp

# Create a proxy module class that passes through to original multiprocessing
# but overrides Pool with Ray's distributed Pool
class _MultiprocessingProxy:
    """Proxy module that wraps multiprocessing, overriding only Pool with Ray's version."""
    
    def __init__(self, original_mp, ray_mp):
        self._original_mp = original_mp
        self._ray_mp = ray_mp
    
    def __getattr__(self, name):
        # Override Pool with Ray's distributed Pool
        if name == 'Pool':
            return self._ray_mp.Pool
        # Everything else comes from original multiprocessing
        return getattr(self._original_mp, name)
    
    def __dir__(self):
        # Expose all original multiprocessing attributes
        return dir(self._original_mp)

# Create and install the proxy
_mp_proxy = _MultiprocessingProxy(_original_mp, ray_mp)
sys.modules['multiprocessing'] = _mp_proxy
print("   ✅ multiprocessing.Pool patched with Ray (all other attrs preserved)")

# Also patch torch.multiprocessing if available
try:
    import torch.multiprocessing
    torch.multiprocessing.Pool = ray_mp.Pool
    # No-op set_start_method since Ray handles this internally
    torch.multiprocessing.set_start_method = lambda *a, **kw: None
    print("   ✅ torch.multiprocessing patched")
except ImportError:
    pass  # torch not installed, skip

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
        sys.stdout.flush()
        sys.stderr.flush()
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

        # Check for likely causes of unpickling failures
        if isinstance(e, (ImportError, ModuleNotFoundError, AttributeError)):
            print("\n" + "="*60)
            print("💡 SlurmRay Diagnosis: Standalone Runner Pattern Recommended")
            print("="*60)
            print("You are likely encountering a 'Bootstrap Paradox' where dill cannot unpickle")
            print("your function because the required modules are not yet in sys.path.")
            print("")
            print("Solution: Move your remote entry point to a standalone script (e.g., scripts/runner.py)")
            print("that sets up sys.path BEFORE importing your package modules.")
            print("See: usage/deployment_patterns.md -> 'Autonomous Script Orchestration Pattern'")
            print("="*60 + "\n")

        import traceback

        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        sys.exit(1)

# Load the arguments
try:
    with open(os.path.join(PROJECT_PATH, "args.pkl"), "rb") as f:
        args = dill.load(f)
except Exception as e:
    print(f"❌ Error loading arguments: {e}")
    # Diagnose potential import errors
    if isinstance(e, (ImportError, ModuleNotFoundError, AttributeError)):
        print("\\n" + "="*60)
        print("💡 SlurmRay Diagnosis: Argument Deserialization Failure")
        print("="*60)
        print("Failed to unpickle arguments. This usually means the arguments contain")
        print("custom classes whose modules are not yet loaded in spython.py.")
        print("="*60 + "\\n")
    
    import traceback
    traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    sys.exit(1)

# Run the function
try:
    result = func(**args)
except Exception as e:
    print(f"Error executing function: {e}")
    import traceback

    traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
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
    sys.stdout.flush()
    sys.stderr.flush()
    sys.exit(1)

# Stop ray
try:
    ray.shutdown()
except Exception as e:
    print(f"Warning: Error shutting down Ray: {e}")
