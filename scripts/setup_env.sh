#!/usr/bin/env bash

# One-click environment setup script for Hikyuu × Qlib workstation.
# Usage: bash scripts/setup_env.sh [env_name]

set -euo pipefail

ENV_NAME=${1:-qlib_hikyuu}
PY_VERSION=${PYTHON_VERSION:-3.11}
REQ_FILE=${REQ_FILE:-requirements.txt}

function log() {
  printf '[setup-env] %s\n' "$1"
}

if command -v conda >/dev/null 2>&1; then
  log "Conda detected. Preparing environment '${ENV_NAME}' (python=${PY_VERSION})."
  if conda info --envs | awk '{print $1}' | grep -Fxq "$ENV_NAME"; then
    log "Environment '${ENV_NAME}' already exists. Skipping creation."
  else
    conda create -y -n "$ENV_NAME" "python=${PY_VERSION}"
  fi
  if [ -f "$REQ_FILE" ]; then
    log "Installing requirements from ${REQ_FILE}."
    conda run -n "$ENV_NAME" pip install -r "$REQ_FILE"
  else
    log "Requirements file ${REQ_FILE} not found. Skipping pip install."
  fi
  log "Environment setup completed. Activate with: conda activate ${ENV_NAME}"
  exit 0
fi

log "Conda not found. Falling back to python -m venv."
PY_CMD=${PYTHON_CMD:-python3}
$PY_CMD -m venv "$ENV_NAME"
source "$ENV_NAME/bin/activate"
if [ -f "$REQ_FILE" ]; then
  log "Installing requirements from ${REQ_FILE}."
  pip install --upgrade pip
  pip install -r "$REQ_FILE"
else
  log "Requirements file ${REQ_FILE} not found. Skipping pip install."
fi
log "Environment setup completed. Activate with: source ${ENV_NAME}/bin/activate"
