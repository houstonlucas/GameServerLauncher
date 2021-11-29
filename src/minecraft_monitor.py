import os
import logging

import sys
from pathlib import Path

sys.path.append(".")

from src.server_monitor import GameMonitor, EC2ServerMonitor
from src.utils import tmux_sendkeys, create_tmux_session


class MinecraftMonitor(GameMonitor):
    def __init__(self, debug_mode=False):
        super().__init__(debug_mode)
        self.debug_mode = debug_mode
        self.port = 25565
        self.tmux_session_name = "minecraft"
        self.logger = logging.getLogger("MinecraftMonitor")

    def start_game_server(self):
        create_tmux_session(self.tmux_session_name)
        tmux_sendkeys(self.tmux_session_name, "cd ~/minecraft")
        tmux_sendkeys(self.tmux_session_name, "java -Xmx4096M -jar server.jar nogui")

    def shutdown_game_server(self):
        # Issue commands to the tmux session
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
    minecraft_monitor = MinecraftMonitor(debug)
    config_path = Path("Configs/EC2_Monitor_Config.json").absolute()
    ec2_monitor = EC2ServerMonitor(minecraft_monitor, config_path)
    ec2_monitor.run()
