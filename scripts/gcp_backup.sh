#!/bin/bash
# gcp_backup.sh
# Copies the active ML model registry to a secondary GCP cold storage bucket
# Designed to be run via a weekly cron job.

BUCKET_NAME="gs://avertai-cold-storage-backup"
MODEL_DIR="/opt/avertai/backend/model_registry"

echo "Initiating GCP cold storage backup for ML models..."

if [ ! -d "$MODEL_DIR" ]; then
    echo "ERROR: Model directory $MODEL_DIR not found."
    exit 1
fi

# Sync the local directory to the GCP bucket
gsutil -m rsync -r "$MODEL_DIR" "$BUCKET_NAME/model_registry_$(date +%Y%m%d)"

if [ $? -eq 0 ]; then
    echo "Backup completed successfully to $BUCKET_NAME."
else
    echo "ERROR: gsutil sync failed."
    exit 1
fi
