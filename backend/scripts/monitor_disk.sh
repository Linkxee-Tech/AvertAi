#!/bin/bash
# monitor_disk.sh
# Check if root disk usage is above 80% and alert
THRESHOLD=80
USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')

if [ "$USAGE" -gt "$THRESHOLD" ]; then
    echo "ALERT: Disk usage is at ${USAGE}%, which is over the ${THRESHOLD}% threshold!"
    exit 1
else
    echo "Disk usage is normal: ${USAGE}%"
    exit 0
fi
