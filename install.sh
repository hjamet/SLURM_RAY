#!/bin/bash
# Installation script for SlurmRay
# Usage: ./install.sh [--force-reinstall]

set -e

FORCE_REINSTALL=false

# Parse arguments
if [ "$1" == "--force-reinstall" ] || [ "$1" == "--clean" ]; then
    FORCE_REINSTALL=true
fi

echo "Installing SlurmRay..."

# Check if Poetry is installed
if ! command -v poetry &> /dev/null; then
    echo "Error: Poetry is not installed. Please install Poetry first."
    echo "Visit: https://python-poetry.org/docs/#installation"
    exit 1
fi

# Force reinstall: remove existing virtual environment
if [ "$FORCE_REINSTALL" = true ]; then
    echo "Force reinstall enabled: removing existing virtual environment..."
    poetry env remove python 2>/dev/null || true
    echo "Virtual environment removed."
fi

# Install dependencies
echo "Installing dependencies..."
poetry install

echo "Installation complete!"

