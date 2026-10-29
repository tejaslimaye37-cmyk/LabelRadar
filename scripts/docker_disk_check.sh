#!/usr/bin/env bash
set -euo pipefail

echo '=== Docker disk accounting ==='
docker system df -v
echo
echo '=== Containers (including stopped) ==='
docker ps -a --size
echo
echo '=== Images ==='
docker images
 echo
echo '=== Volumes ==='
docker volume ls
