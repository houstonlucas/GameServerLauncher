import os
import logging
import pathlib
import time

import sys
from pathlib import Path
from typing import List, Union

sys.path.append(".")

from src.server_monitor import GameMonitor, EC2ServerMonitor
from src.utils import tmux_sendkeys, create_tmux_session, json_from_file


class MinecraftMonitor(GameMonitor):

    def __init__(self, config_file: Union[str, Path], debug_mode=False):
        super().__init__(debug_mode)
        self.config = json_from_file(config_file)
        self.debug_mode = debug_mode
        self.port = 25565
        self.tmux_session_name = "minecraft"
        self.logger = logging.getLogger("MinecraftMonitor")
        if self.debug_mode:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.WARNING)
        self.logger.addHandler(logging.StreamHandler(sys.stdout))
        self.logger.addHandler(
            logging.FileHandler(self.config['log_file'])
        )

    def parse_custom_commands(self, command_words: List[str]):
        if "restart" in command_words:
            self.restart_game_server()
            return True, "Server is restarting."
        else:
            return False, ""

    def start_game_server(self):
        self.logger.debug("Starting game server")
        minecraft_path = self.config['server_dir']
        mem_size = self.config['server_memory']
        create_tmux_session(self.tmux_session_name)
        tmux_sendkeys(self.tmux_session_name, f"cd {minecraft_path}")
        tmux_sendkeys(self.tmux_session_name, f'java -Xmx{mem_size}M -jar server.jar nogui')

    def shutdown_game_server(self):
        # Issue commands to the tmux session
        self.logger.debug("Shutting down game server")
        tmux_sendkeys(self.tmux_session_name, "stop")
        while self.server_running:
            time.sleep(self.config["heartbeat"])
        self.logger.debug("Server has shutdown.")

    # TODO: This might be better as a method in the base class.
    # You'd have to make sure the shutdown method waits until it's actually shutdown though.
    def restart_game_server(self):
        self.logger.debug("Starting server restart sequence.")
        self.shutdown_game_server()
        self.logger.debug("Server successfully shutdown. Continuing with restarting server.")
        self.start_game_server()

    @property
    def server_empty(self):
        # Count the number of tcp connections on the port
        val = os.popen(f'lsof -iTCP:{self.port} -sTCP:ESTABLISHED').read()
        return val.count("ESTABLISHED") == 0

    @property
    def server_running(self):
        # See if there is a listener on the port
        val = os.popen(f'lsof -iTCP:{self.port} -sTCP:LISTEN').read()
        return bool(val)


if __name__ == '__main__':
    debug = False
    minecraft_config = Path("Configs/Games/minecraft.json")
    minecraft_monitor = MinecraftMonitor(minecraft_config, debug)
    config_path = Path("Configs/EC2_Monitor_Config.json").absolute()
    ec2_monitor = EC2ServerMonitor(minecraft_monitor, config_path)
    ec2_monitor.run()
