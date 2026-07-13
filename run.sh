#!/usr/bin/env bash
# Launch the GP-50 Converter web app.
#
# Usage: ./run.sh
# Serves on http://127.0.0.1:8756 with autoreload. Requires .venv-app
# (create it with: python3 -m venv .venv-app && ./.venv-app/bin/python -m pip
# install fastapi "uvicorn[standard]" python-multipart pytest httpx).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source .venv-app/bin/activate
exec uvicorn app.main:app --reload --port 8756
