#!/bin/bash

# ====================================================================
# SLURM_RAY - Reverse SSH Tunnel Setup
# ====================================================================
# This script establishes a reverse SSH tunnel using autossh.
# It is designed to run in the foreground to be easily managed by PM2.
#
# Requirements: autossh
# Run with PM2: pm2 start scripts/setup_reverse_tunnel.sh --name "desi-tunnel"
# ====================================================================

# Check required environment variables
if [ -z "$SERVER_SSH" ] || [ -z "$SERVER_PORT" ] || [ -z "$SERVER_USERNAME" ]; then
    echo "ERROR: Missing required environment variables."
    echo "Please ensure SERVER_SSH, SERVER_PORT, and SERVER_USERNAME are set."
    echo ""
    echo "Example:"
    echo "  export SERVER_SSH=my-bridge-server.com"
    echo "  export SERVER_PORT=12345"
    echo "  export SERVER_USERNAME=bridgeuser"
    exit 1
fi

echo "Starting Reverse SSH Tunnel..."
echo "Target: $SERVER_USERNAME@$SERVER_SSH"
echo "Remote Port: $SERVER_PORT -> Local Port: 22"

# AUTOSSH_GATETIME=0 ensures autossh keeps retrying even if the first connection fails
export AUTOSSH_GATETIME=0

# Execute autossh
# -M 0: Disable autossh monitoring port, rely on SSH ServerAliveInterval
# -N: Do not execute a remote command
# -o ServerAliveInterval=30: Send keep-alive packets every 30 seconds
# -o ServerAliveCountMax=3: Disconnect after 3 missed keep-alive packets
# -o ExitOnForwardFailure=yes: Exit if port forwarding fails, allowing autossh to restart it
# -R: Reverse port forwarding
exec autossh -M 0 -N \
    -o "ServerAliveInterval 30" \
    -o "ServerAliveCountMax 3" \
    -o "ExitOnForwardFailure yes" \
    -R "${SERVER_PORT}:localhost:22" \
    "${SERVER_USERNAME}@${SERVER_SSH}"
