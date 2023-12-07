#!/bin/sh

echo "Installing slurmray server"

# Copy files
mv -t slurmray-server requirements.txt slurmray_server.py
mv -t slurmray-server/.slogs/server func.pkl args.pkl 
cd slurmray-server

# Load modules
module load gcc python/3.9.13 cuda cudnn

# Check if venv exists
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# Install requirements
pip3 install -r requirements.txt

# Run server
python -u slurmray_server.py