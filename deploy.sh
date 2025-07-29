#!/bin/bash

cd /home/azureuser/aayu_app  # Not fastapi — go to the repo root

echo "==== Directory ===="
pwd
echo "==== Git Remote ===="
git remote -v
echo "==== Branch ===="
git branch

echo "Pulling latest changes from prod branch..."
git fetch origin prod
git reset --hard origin/prod

docker compose down
docker compose up --build -d

echo "Deployment completed."
