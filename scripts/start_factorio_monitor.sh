#!/bin/bash
cd /home/ubuntu/GameServerLauncher
export PYTHONPATH="`pwd`/"
. venv/bin/activate
python3 src/factorio_monitor.py
