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
# Check for force reinstall flag
if [ -f ".force_reinstall" ]; then
    echo "Force reinstall flag detected: removing existing virtualenv..."
    rm -rf .venv
    rm -f .force_reinstall
fi

if [ ! -d ".venv" ]; then
    echo "Creating virtualenv..."
    python3 -m venv .venv
else
    echo "Using existing virtualenv (requirements unchanged)..."
    VENV_EXISTED=true
fi

source .venv/bin/activate

# Install requirements if file exists and is not empty
if [ -f requirements.txt ]; then
    # Check if requirements.txt is empty (only whitespace)
    if [ -s requirements.txt ]; then
        echo "📥 Installing dependencies from requirements.txt..."
        # Install wheel first (required for some packages)
        if ! pip install --quiet wheel >/dev/null 2>&1; then
            echo "  ❌ wheel"
            pip install wheel 2>&1 | grep -E "(error|Error|ERROR|failed|Failed|FAILED)" | head -3 | sed 's/^/      /' || true
            exit 1
        fi
        
        INSTALL_ERRORS=0
        SKIPPED_COUNT=0
        while IFS= read -r line || [ -n "$line" ]; do
            # Skip empty lines and comments
            line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
            if [ -z "$line" ] || [ "${line#\#}" != "$line" ]; then
                continue
            fi
            
            # Extract package name for display (remove version specifiers and extras)
            pkg_name=$(echo "$line" | sed 's/[<>=!].*//' | sed 's/\[.*\]//' | sed 's/[[:space:]]*//')
            if [ -z "$pkg_name" ]; then
                continue
            fi
            
            # Check if package is already installed with correct version
            # Extract version requirement if present
            if echo "$line" | grep -q "=="; then
                required_version=$(echo "$line" | sed 's/.*==\([^;]*\).*/\1/' | sed 's/[[:space:]]*//')
                installed_version=$(pip show "$pkg_name" 2>/dev/null | grep "^Version:" | sed 's/Version: //' | sed 's/[[:space:]]*//')
                if [ -n "$installed_version" ] && [ "$installed_version" = "$required_version" ]; then
                    echo "  ⏭️  $pkg_name==$installed_version (already installed)"
                    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
                    continue
                fi
            else
                # No version specified, just check if package exists
                if pip show "$pkg_name" >/dev/null 2>&1; then
                    installed_version=$(pip show "$pkg_name" 2>/dev/null | grep "^Version:" | sed 's/Version: //' | sed 's/[[:space:]]*//')
                    echo "  ⏭️  $pkg_name==$installed_version (already installed)"
                    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
                    continue
                fi
            fi
            
            # Package not installed or version mismatch, install it
            if pip install --progress-bar off --quiet "$line" >/dev/null 2>&1; then
                echo "  ✅ $pkg_name"
            else
                echo "  ❌ $pkg_name"
                INSTALL_ERRORS=$((INSTALL_ERRORS + 1))
                # Show error details
                pip install --progress-bar off "$line" 2>&1 | grep -E "(error|Error|ERROR|failed|Failed|FAILED)" | head -3 | sed 's/^/      /' || true
            fi
        done < requirements.txt
        
        if [ $INSTALL_ERRORS -eq 0 ]; then
            if [ $SKIPPED_COUNT -gt 0 ]; then
                echo "✅ All dependencies up to date ($SKIPPED_COUNT already installed, $((INSTALL_ERRORS + SKIPPED_COUNT - SKIPPED_COUNT)) newly installed)"
            else
                echo "✅ All dependencies installed successfully"
            fi
        else
            echo "❌ Failed to install $INSTALL_ERRORS package(s)" >&2
            exit 1
        fi
    else
        if [ "$VENV_EXISTED" = "true" ]; then
            echo "✅ All dependencies already installed (requirements.txt is empty)"
        else
            echo "⚠️  requirements.txt is empty, skipping dependency installation"
        fi
    fi
else
    echo "⚠️  No requirements.txt found, skipping dependency installation"
fi

# Fix torch bug (https://github.com/pytorch/pytorch/issues/111469)
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
export LD_LIBRARY_PATH=$HOME/slurmray-server/.venv/lib/python$PYTHON_VERSION/site-packages/nvidia/nvjitlink/lib:$LD_LIBRARY_PATH


# Run server
python -u slurmray_server.py