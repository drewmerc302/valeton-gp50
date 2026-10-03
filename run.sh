#!/usr/bin/env bash
# Launch the GP-50 Converter web app.
#
# Usage: ./run.sh
# Serves on http://127.0.0.1:8756 with autoreload. Requires .venv-app
# (create it with: python3 -m venv .venv-app && ./.venv-app/bin/python -m pip
# install -r requirements-app.txt).
# AI patch generation needs AWS_REGION + credentials (boto3 chain) — e.g.:
#   AWS_REGION=us-east-1 AWS_PROFILE=igor ./run.sh
# Set APP_AUTH_PASSWORD to gate the whole app behind HTTP Basic (as on the hosted
# backend); leave it unset for open local dev. Username defaults to "valeton":
#   APP_AUTH_PASSWORD='a-long-random-secret' ./run.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source .venv-app/bin/activate
exec uvicorn app.main:app --reload --port 8756
