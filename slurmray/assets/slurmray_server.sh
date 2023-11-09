#!/bin/sh

echo "Installing slurmray server"

# Create a folder if not exists
mkdir -p slurmray-server/.slogs/server
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

# Run server
python slurmray_server.py 2>&1