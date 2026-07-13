#!/bin/bash
# rollback.sh
# Reverts the production backend to the previously deployed Docker image

echo "Initiating rollback of backend service..."

cd /opt/avertai || exit 1

# Find the previously running image (or simply fallback to :previous tag if used in registry)
# Assuming standard practice of tagging last known good image as :previous during CI
docker pull registry.digitalocean.com/avertai/backend:previous

if [ $? -ne 0 ]; then
    echo "ERROR: Could not pull the previous image tag."
    exit 1
fi

# Update docker-compose to point to previous tag temporarily and restart
sed -i 's/backend:latest/backend:previous/g' docker-compose.yml
docker-compose up -d

echo "Rollback complete. The backend is now running the :previous image."
echo "Remember to revert the docker-compose.yml tag back to latest after fixing the upstream bug!"
