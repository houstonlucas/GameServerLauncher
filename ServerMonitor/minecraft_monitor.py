import os
import logging

from ServerMonitor.server_monitor import GameMonitor, EC2ServerMonitor
from utils import tmux_sendkeys, create_tmux_session


class MinecraftMonitor(GameMonitor):
    def __init__(self):
        super().__init__()
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
        # Count the number of tcp connections on port 25565
        val = os.popen('lsof -iTCP:25565 -sTCP:ESTABLISHED').read()
        return val.count("ESTABLISHED") == 0

    @property
    def server_running(self):
        # See if there is a listener on port 25565
        val = os.popen('lsof -iTCP:25565 -sTCP:LISTEN').read()
        return bool(val)


if __name__ == '__main__':
    minecraft_monitor = MinecraftMonitor()
    ec2_monitor = EC2ServerMonitor(minecraft_monitor, "../configs/EC2_Monitor_Config.json")
    ec2_monitor.monitor_game()

