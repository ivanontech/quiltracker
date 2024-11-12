#!/bin/bash

LOG_FILE="/root/track_balances.log"

# Navigate to the correct directory
cd /root/ceremonyclient/node || exit 1  # Exit if directory change fails

# Fetch balance and peer ID
PEER_ID=$(./node-2.0.3.3-linux-amd64 -peer-id | grep "Peer ID" | awk '{print $3}')
BALANCE=$(./node-2.0.3.3-linux-amd64 -balance | grep "Unclaimed balance" | awk '{print $3}')

DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Log peer ID and balance
echo "[$DATE] Peer ID: $PEER_ID, Balance: $BALANCE" >> $LOG_FILE

# Send the data to the Flask server
curl -X POST -H "Content-Type: application/json" \
-d "{\"peer_id\":\"$PEER_ID\", \"balance\":\"$BALANCE\", \"timestamp\":\"$DATE\"}" \
http://0.0.0.0:5000/update_balance >> $LOG_FILE 2>&1
