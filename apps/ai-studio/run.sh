#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p outputs

source .venv/bin/activate
cd src
uvicorn app:app --host 127.0.0.1 --port 8420
