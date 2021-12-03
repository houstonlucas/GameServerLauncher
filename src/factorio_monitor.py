import os
import re
import logging
import pathlib

import sys
import time
from pathlib import Path

sys.path.append(".")

from src.server_monitor import GameMonitor, EC2ServerMonitor
from src.utils import tmux_sendkeys, json_from_file


class FactorioMonitor(GameMonitor):
    def __init__(self, config_file: str, debug_mode: bool = False):
        super().__init__(debug_mode)
        # TODO: don't pass save file in directly, pass in a config file
        self.config = json_from_file(config_file)
        self.save_file = self.config['save_file']
        self.tmux_log = "../logs/tmux_factorio.log"
        assert (pathlib.Path(self.save_file).exists())
        self.port = 34197
        self.tmux_session_name = "factorio"
        self.logger = logging.getLogger("MinecraftMonitor")

    def start_game_server(self):
        start_server_cmd = f"/home/ubuntu/factorio/bin/x64/factorio --start-server {self.save_file}"
        os.system(f'tmux new-session -s {self.tmux_session_name} -d')
        tmux_sendkeys(self.tmux_session_name, f"{start_server_cmd} 2>&1 | tee {self.tmux_log}")

    def shutdown_game_server(self):
        # Issue commands to the tmux session
        tmux_sendkeys(self.tmux_session_name, '/save')
        time.sleep(5.0)
        tmux_sendkeys(self.tmux_session_name, '/quit')

    def parse_command(self, data: bytes):
        # TODO: actually parse command. This is for testing.
        print(data)
        return data

    @property
    def server_empty(self):
        # The number of lines back in the log to use to evaluate the number of players online
        num_lines = 10
        tmux_sendkeys(self.tmux_session_name, "/p o")
        # Small sleep to allow response
        time.sleep(0.1)
        lines = os.popen(f'tail -n {num_lines} {self.tmux_log}').read().split("\n")
        regex_search = r"Online players \((\d+)\)"
        for line in lines[::-1]:
            player_count_search = re.search(regex_search, line)
            if player_count_search:
                player_count = player_count_search.group(1)
                return player_count == '0'
        return True

    @property
    def server_running(self):
        # See if there is a listener on the port
        val = os.popen(f'lsof -i:{self.port}').read()
        return bool(val)


if __name__ == '__main__':
    debug = True
    factorio_config = Path("Configs/Games/factorio_config.json")
    factorio_monitor = FactorioMonitor(factorio_config, debug)
    config_path = Path("Configs/EC2_Monitor_Config.json").absolute()
    ec2_monitor = EC2ServerMonitor(factorio_monitor, config_path)
    ec2_monitor.run()
