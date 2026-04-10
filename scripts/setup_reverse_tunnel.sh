#!/bin/bash
# scripts/setup_reverse_tunnel.sh
#
# Stealth Reverse SSH Tunnel Setup Script for SlurmRay
#
# This script configures an internal server (like Desi) to expose its SSH
# port to an external relay server (like Hetzner) using a reverse SSH tunnel.
# This allows SlurmRay to connect to the internal server from anywhere via the relay.

set -e

# Configuration (to be modified by the user before running)
RELAY_USER="root"
RELAY_HOST="<RELAY_IP_OR_DOMAIN>"
RELAY_PORT=22             # SSH port of the relay server
REVERSE_PORT=2222         # Port on the relay server that will map back to this server's SSH
LOCAL_SSH_PORT=22         # Local SSH port of the internal server (usually 22)

echo "=========================================================="
echo " SlurmRay - Stealth Reverse SSH Tunnel Setup"
echo "=========================================================="

# Check for autossh
if ! command -v autossh &> /dev/null; then
    echo "❌ autossh is not installed."
    echo "Please install it first: sudo apt-get install autossh (Ubuntu/Debian) or equivalent."
    exit 1
else
    echo "✅ autossh is installed."
fi

# Check for npm/pm2
if ! command -v pm2 &> /dev/null; then
    echo "❌ pm2 is not installed."
    echo "Please install Node.js and then pm2: npm install -g pm2"
    exit 1
else
    echo "✅ pm2 is installed."
fi

echo "=========================================================="
echo "Configuration summary:"
echo "Relay Server: ${RELAY_USER}@${RELAY_HOST}:${RELAY_PORT}"
echo "Reverse Port: ${REVERSE_PORT} (on relay) -> ${LOCAL_SSH_PORT} (local)"
echo "=========================================================="

echo "To establish the tunnel, run the following command to test it interactively:"
echo "  autossh -M 0 -N -q -o \"ServerAliveInterval 30\" -o \"ServerAliveCountMax 3\" -p ${RELAY_PORT} -R ${REVERSE_PORT}:localhost:${LOCAL_SSH_PORT} ${RELAY_USER}@${RELAY_HOST}"

echo ""
echo "To daemonize the process with pm2 (so it persists across reboots), run:"
echo "  pm2 start autossh --name \"slurmray-tunnel\" -- -M 0 -N -q -o \"ServerAliveInterval 30\" -o \"ServerAliveCountMax 3\" -p ${RELAY_PORT} -R ${REVERSE_PORT}:localhost:${LOCAL_SSH_PORT} ${RELAY_USER}@${RELAY_HOST}"
echo ""
echo "Then, to save the pm2 list and ensure it starts on boot:"
echo "  pm2 save"
echo "  pm2 startup"
echo ""
echo "=========================================================="
echo "Note: Make sure your SSH keys are set up between this server and the relay server."
echo "You can copy your public key using:"
echo "  ssh-copy-id -p ${RELAY_PORT} ${RELAY_USER}@${RELAY_HOST}"
echo "=========================================================="
echo "To configure SlurmRay to use this tunnel, add or override these variables in your .env or environment:"
echo "  SERVER_SSH=${RELAY_HOST}"
echo "  SERVER_PORT=${REVERSE_PORT}"
echo "  SERVER_USERNAME=${RELAY_USER}"
echo "=========================================================="
