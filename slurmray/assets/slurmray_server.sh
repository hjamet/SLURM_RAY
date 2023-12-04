#!/bin/sh

echo "Installing slurmray server"

# Copy files
mv -t slurmray-server requirements.txt slurmray_server.py
mv -t slurmray-server/.slogs/server func.pkl args.pkl 
cd slurmray-server

# Load modules
module load gcc python/3.9.13

# Check if venv exists
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Change torch to cluster version
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118 --upgrade

# Run server
python -u slurmray_server.py