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
## Load all installed packages into a variable
installed_packages=$(pip3 list --format=freeze)
## Function to check if a package is installed
is_package_installed() {
  package=$1
  echo "$installed_packages" | grep -i "^$package==" &> /dev/null
  return $?
}
## Read the requirements.txt file line by line
while IFS= read -r package
do
  # Check if the line is not empty
  if [ -n "$package" ]; then
    echo "Checking package: $package"
    # Extract the package name without options
    package_name=$(echo "$package" | awk '{print $1}' | cut -d'=' -f1)
    if is_package_installed "$package_name"; then
      echo "The package $package_name is already installed."
    else
      echo "Installing package: $package"
      command="pip3 install $package"
      eval "$command"
      if [ $? -ne 0 ]; then
        echo "Error while installing $package"
      fi
    fi
  fi
done < "requirements.txt"

# Fix torch bug (https://github.com/pytorch/pytorch/issues/111469)
export LD_LIBRARY_PATH=$HOME/slurmray-server/.venv/lib/python3.9/site-packages/nvidia/nvjitlink/lib:$LD_LIBRARY_PATH


# Run server
python -u slurmray_server.py