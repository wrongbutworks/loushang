#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
exec bash -ic 'source .venv/bin/activate && python3 demo.py "$@"' bash "$@"
