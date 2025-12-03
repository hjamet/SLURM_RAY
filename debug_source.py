import dill
import ray
import torch
import os

def function_inside_function():
    return "DocNotFound"

def example_func(x):
    result = (
        ray.cluster_resources(),
        f"GPU is available : {torch.cuda.is_available()}",
        x + 1,
        function_inside_function(),
    )
    return result

# Pickle
dill.settings["recurse"] = True
with open("test.pkl", "wb") as f:
    dill.dump(example_func, f)

# Unpickle in a clean environment
import subprocess
import sys

code = """
import dill
import sys
import os

# Mock ray and torch?
# No, import them as in spython_template
import ray
import torch

with open("test.pkl", "rb") as f:
    func = dill.load(f)

print("Loaded func")
try:
    # We need to mock args?
    # x=1
    res = func(1)
    print("Result:", res)
except Exception as e:
    print("Error:", e)
    import traceback
    traceback.print_exc()
"""

with open("runner.py", "w") as f:
    f.write(code)

print("Running runner...")
subprocess.check_call([sys.executable, "runner.py"])

