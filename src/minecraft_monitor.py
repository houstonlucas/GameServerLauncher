import os
import logging
import pathlib

import sys
from pathlib import Path
from typing import Union

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

    def parse_command(self, command: str):
        command_words = command.split()
        if "start" in command_words:
            if self.server_running:
                return "Server started successfully."
            else:
                self.logger.error("Server failed to start")
                return "Error: server did not start successfully."
        elif "stop" in command_words:
            self.shutdown_game_server()
            return "Server has shutdown."
        elif "echo" in command_words:
            return command
        else:
            self.logger.warning("Unrecognized command")
            return 'Command not recognized.'

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
    debug = True
    minecraft_config = Path("Configs/Games/minecraft.json")
    minecraft_monitor = MinecraftMonitor(minecraft_config, debug)
    config_path = Path("Configs/EC2_Monitor_Config.json").absolute()
    ec2_monitor = EC2ServerMonitor(minecraft_monitor, config_path)
    ec2_monitor.run()
