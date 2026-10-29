#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/venv/bin/mlx_lm.server" ]]; then
  echo "Missing venv/bin/mlx_lm.server. Activate your project venv and install mlx-lm first." >&2
  exit 1
fi

# MLX must run on macOS host; Dockerized FastAPI reaches it via host.docker.internal.
if ! curl -fsS http://127.0.0.1:8080/v1/models >/dev/null 2>&1; then
  mkdir -p logs
  nohup "$ROOT/venv/bin/mlx_lm.server" \
    --model mlx-community/Qwen3.5-4B-8bit \
    --host 0.0.0.0 --port 8080 > logs/mlx_server.log 2>&1 &
  echo $! > logs/mlx_server.pid
  echo "Started MLX server; waiting for model API..."
  for _ in $(seq 1 60); do
    if curl -fsS http://127.0.0.1:8080/v1/models >/dev/null 2>&1; then break; fi
    sleep 2
  done
fi
curl -fsS http://127.0.0.1:8080/v1/models >/dev/null || { echo "MLX server did not become ready. See logs/mlx_server.log" >&2; exit 1; }

# Override any host-local .env URL with the host address reachable from Docker.
export OPENAI_BASE_URL="http://host.docker.internal:8080/v1"
export OPENAI_API_KEY="local"
export LLM_MODEL="mlx-community/Qwen3.5-4B-8bit"
docker compose up -d --build

echo
echo "LabelRadar dashboard: http://localhost:8000/dashboard"
echo "Swagger docs:         http://localhost:8000/docs"
echo "Neo4j Browser:        http://localhost:7474"
echo "MLX server log:       $ROOT/logs/mlx_server.log"
echo "Stop Docker services: docker compose down"
echo "Stop MLX server:      kill \$(cat logs/mlx_server.pid) (if started by this script)"
