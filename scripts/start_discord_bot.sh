#!/bin/bash
cd ~/GameServerLauncher
export PYTHONPATH="`pwd`/"
. venv/bin/activate
python3 src/discord_bot.py Configs/DiscordBot/default.json
