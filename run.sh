#!/bin/bash
set -euo pipefail

export PORT="${PORT:-8080}"

exec python -m uvicorn app.backend.main:app --host 0.0.0.0 --port "${PORT}"
