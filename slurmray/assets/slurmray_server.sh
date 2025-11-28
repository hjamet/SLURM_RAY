#!/bin/sh

echo "Installing slurmray server"

# Copy files
mv -t slurmray-server requirements.txt slurmray_server.py
mv -t slurmray-server/.slogs/server func.pkl args.pkl 
cd slurmray-server

# Load modules
# Using specific versions for Curnagl compatibility (SLURM 24.05.3)
# gcc/13.2.0: Latest GCC version
# python/3.12.1: Latest Python version on Curnagl
# cuda/12.6.2: Latest CUDA version
# cudnn/9.2.0.82-12: Compatible with cuda/12.6.2
module load gcc/13.2.0 rust python/3.12.1 cuda/12.6.2 cudnn/9.2.0.82-12

# Create venv if it doesn't exist (hash check is done in Python before file upload)
# If venv needs recreation, it has already been removed by Python
if [ ! -d ".venv" ]; then
    echo "Creating virtualenv..."
    python3 -m venv .venv
else
    echo "Using existing virtualenv (requirements unchanged)..."
fi

source .venv/bin/activate

# Install requirements (pip will skip packages that are already installed)
# Note: requirements.txt is already optimized by Python to only include missing packages
pip install wheel
pip install -r requirements.txt

# Fix torch bug (https://github.com/pytorch/pytorch/issues/111469)
export LD_LIBRARY_PATH=$HOME/slurmray-server/.venv/lib/python3.9/site-packages/nvidia/nvjitlink/lib:$LD_LIBRARY_PATH


# Run server
python -u slurmray_server.py