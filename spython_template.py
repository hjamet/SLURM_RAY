import ray
import dill
import os

PROJECT_PATH = {{PROJECT_PATH}}

# Load the function
with open(os.path.join(PROJECT_PATH, "func.pkl"), "rb") as f:
    func = dill.load(f)

# Load the arguments
with open(os.path.join(PROJECT_PATH, "args.pkl"), "rb") as f:
    args = dill.load(f)
    
# Make sure the function is a remote function
func = ray.remote(func)

# Call the function
result = func.remote(*args)

# Wait for the result
value = ray.get(result)

# Write the result
with open(os.path.join(PROJECT_PATH, "result.pkl"), "wb") as f:
    dill.dump(value, f)