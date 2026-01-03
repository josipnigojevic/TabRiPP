#!/bin/bash
# setup_env.sh: Create a Python venv, install requirements, run downloader.py, and clean up.
set -e

ENV_NAME=".venv-tabRiPP"

cleanup() {
    echo "Cleaning up the environment..."
    deactivate 2>/dev/null || true
    rm -rf "$ENV_NAME"
    echo "tabRiPP environment removed."
}
trap cleanup EXIT

# create virtual environment
python3 -m venv "$ENV_NAME"
source "$ENV_NAME/bin/activate"

# install dependencies
if [ -f requirements.txt ]; then
    pip install --quiet -r requirements.txt
fi

echo "Running downloader.py..."
python3 downloader.py
