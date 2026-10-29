
#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FINGERPRINT_FILE="$ROOT/.labelradar-build-fingerprint"
MLX_URL="http://127.0.0.1:8080/v1/models"
MLX_LOG="$ROOT/logs/mlx_server.log"
MLX_PID_FILE="$ROOT/logs/mlx_server.pid"

# --------------------------------------------------
# 1. Verify Docker is available
# --------------------------------------------------
if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop is not running. Start Docker Desktop and retry." >&2
  exit 1
fi

# --------------------------------------------------
# 2. Compute a fingerprint of project build inputs
# --------------------------------------------------
compute_fingerprint() {
  python3 - "$ROOT" <<'PY'
import hashlib
import os
import sys

root = sys.argv[1]
excluded_dirs = {
    ".git", "venv", ".venv", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "node_modules", "logs",
}
excluded_files = {
    ".labelradar-build-fingerprint", ".DS_Store",
}
digest = hashlib.sha256()

for current, dirs, files in os.walk(root):
    dirs[:] = sorted(d for d in dirs if d not in excluded_dirs)

    for name in sorted(files):
        if name in excluded_files or name.endswith(".pyc"):
            continue

        path = os.path.join(current, name)
        relative = os.path.relpath(path, root)

        digest.update(relative.encode())
        digest.update(b"\0")

        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(chunk)
        except (OSError, IsADirectoryError):
            print(f"Cannot read build input: {relative}", file=sys.stderr)
            sys.exit(1)

        digest.update(b"\0")

print(digest.hexdigest())
PY
}

CURRENT_FINGERPRINT="$(compute_fingerprint)"

# --------------------------------------------------
# 3. Build only when inputs have changed
# --------------------------------------------------
if [[ ! -f "$FINGERPRINT_FILE" ]] ||
   [[ "$(cat "$FINGERPRINT_FILE")" != "$CURRENT_FINGERPRINT" ]]; then
  echo "Project files changed (or no fingerprint exists). Building Docker image..."
  docker compose build
  printf '%s\n' "$CURRENT_FINGERPRINT" > "$FINGERPRINT_FILE"
else
  echo "No project file changes detected. Skipping Docker build."
fi

# --------------------------------------------------
# 4. Start MLX on the macOS host if needed
# --------------------------------------------------
if [[ ! -x "$ROOT/venv/bin/mlx_lm.server" ]]; then
  echo "Missing venv/bin/mlx_lm.server. Install mlx-lm in your project venv." >&2
  exit 1
fi

mkdir -p "$ROOT/logs"

if ! curl -fsS "$MLX_URL" >/dev/null 2>&1; then
  echo "Starting MLX server..."
  nohup "$ROOT/venv/bin/mlx_lm.server" \
    --model mlx-community/Qwen3.5-4B-8bit \
    --host 0.0.0.0 \
    --port 8080 > "$MLX_LOG" 2>&1 </dev/null &
  echo $! > "$MLX_PID_FILE"

  ready=false
  for _ in $(seq 1 120); do
    if curl -fsS "$MLX_URL" >/dev/null 2>&1; then
      ready=true
      break
    fi
    sleep 2
  done

  if [[ "$ready" != true ]]; then
    echo "MLX did not become ready. Check $MLX_LOG" >&2
    exit 1
  fi
fi

echo "MLX server is ready."

# --------------------------------------------------
# 5. Configure the container-to-host LLM connection
# --------------------------------------------------
export OPENAI_BASE_URL="http://host.docker.internal:8080/v1"
export OPENAI_API_KEY="local"
export LLM_MODEL="mlx-community/Qwen3.5-4B-8bit"

# --------------------------------------------------
# 6. Start containers without forcing a rebuild
# --------------------------------------------------
docker compose up -d

echo
echo "LabelRadar dashboard: http://localhost:8000/dashboard"
echo "Swagger docs:         http://localhost:8000/docs"
echo "Neo4j Browser:        http://localhost:7474"
echo "MLX server log:       $MLX_LOG"
echo
echo "Stop Docker services: docker compose down"
echo "Stop MLX (if started by this script): kill \$(cat logs/mlx_server.pid)"
