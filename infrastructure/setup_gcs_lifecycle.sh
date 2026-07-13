#!/bin/bash
# Phase 2.8: GCS Bucket Lifecycle Rule
# Auto-archives (deletes) satellite images older than 30 days.

BUCKET_NAME=$1

if [ -z "$BUCKET_NAME" ]; then
  echo "Usage: $0 <bucket-name>"
  exit 1
fi

echo "Applying lifecycle config to gs://$BUCKET_NAME..."

# Requires gcloud CLI installed and authenticated
gcloud storage buckets update gs://$BUCKET_NAME --lifecycle-file=gcs_lifecycle.json

echo "Lifecycle config applied successfully. Satellite images older than 30 days will be auto-deleted."
