#!/usr/bin/env bash
# =================================
# Arcane Eye Linux Launcher
# =================================

echo "Launching Arcane Eye..."

# Activate virtualenv if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Run the module
python3 -m arcaneeye
status=$?

if [ $status -ne 0 ]; then
    echo
    echo "[ERROR] Arcane Eye exited with code $status"
fi