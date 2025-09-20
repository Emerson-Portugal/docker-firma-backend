#!/bin/bash
set -e
git pull
sudo systemctl restart docker
docker-compose down
docker-compose build --no-cache
docker-compose up -d
