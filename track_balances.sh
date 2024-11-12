#!/bin/bash

LOG_FILE="/root/track_balances.log"

# Navigate to the correct directory
cd /root/ceremonyclient/node || exit 1  # Exit if directory change fails

# Run the command to get node info
NODE_INFO_OUTPUT=$(./node-2.0.3.3-linux-amd64 -node-info)

# Extract Peer ID, Version, Max Frame, Prover Ring, Seniority, and Owned Balance
PEER_ID=$(echo "$NODE_INFO_OUTPUT" | grep "Peer ID" | awk '{print $3}')
VERSION=$(echo "$NODE_INFO_OUTPUT" | grep "Version" | awk '{print $2}')
MAX_FRAME=$(echo "$NODE_INFO_OUTPUT" | grep "Max Frame" | awk '{print $3}')
PROVER_RING=$(echo "$NODE_INFO_OUTPUT" | grep "Prover Ring" | awk '{print $3}')
SENIORITY=$(echo "$NODE_INFO_OUTPUT" | grep "Seniority" | awk '{print $2}')
BALANCE=$(echo "$NODE_INFO_OUTPUT" | grep "Owned balance" | awk '{print $3}')

DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Log all extracted information
echo "[$DATE] Peer ID: $PEER_ID, Version: $VERSION, Max Frame: $MAX_FRAME, Prover Ring: $PROVER_RING, Seniority: $SENIO>

# Send the data to the Flask server
curl -X POST -H "Content-Type: application/json" \
-d "{\"peer_id\":\"$PEER_ID\", \"version\":\"$VERSION\", \"max_frame\":\"$MAX_FRAME\", \"prover_ring\":\"$PROVER_RING\">http://0.0.0.0:5000/update_balance >> $LOG_FILE 2>&1
