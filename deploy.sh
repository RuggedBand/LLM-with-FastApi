#!/bin/bash
echo "Pulling latest changes from prod branch..."
cd /home/azureuser/aayu_app/fastapi

git fetch origin prod
git reset --hard origin/prod

docker compose down
docker compose up --build -d

echo "Deployment completed."
