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
