from abc import ABC, abstractmethod
import json
import logging
import os
import time

from ServerMonitors.utils import get_now_str, Timer


class GameMonitor(ABC):
    def __init__(self, debug_mode):
        self.debug_mode = debug_mode

    @abstractmethod
    def start_game_server(self):
        raise NotImplementedError

    @abstractmethod
    def shutdown_game_server(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def server_empty(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def server_running(self):
        raise NotImplementedError


class EC2ServerMonitor:
    def __init__(self, game_monitor: GameMonitor, config_file: str):
        with open(config_file) as f:
            self.config = json.load(f)
        self.game_monitor = game_monitor
        self.should_shutdown = False
        self.empty_timer = Timer(self.config["max_empty_time"])
        self.down_timer = Timer(self.config["max_downtime"])
        self.logger = logging.getLogger("EC2Monitor")

    def monitor_game(self):
        # Start game server
        self.game_monitor.start_game_server()

        # Wait for game server to start
        self.down_timer.start()
        while not self.game_monitor.server_running:
            # Shut off EC2 instance if server doesn't start.
            if self.down_timer.expired:
                self.should_shutdown = True
                self.shutdown_ec2_instance("Game server failed to start.")

            time.sleep(self.config["heartbeat"])

        self.down_timer.reset()
        self.logger.info("Game server started.")

        # Monitor for extended empty server
        while not self.should_shutdown:
            # If server isn't running
            if not self.game_monitor.server_running:
                # Evaluated if server has been down long enough to shutdown
                if not self.down_timer.is_running:
                    self.down_timer.start()
                else:
                    if self.down_timer.expired:
                        self.should_shutdown = True
                        self.shutdown_ec2_instance("Game server seems to have crashed.")
            # If server is empty
            elif self.game_monitor.server_empty:
                if not self.empty_timer.is_running:
                    self.empty_timer.start()
                else:
                    if self.empty_timer.expired:
                        self.should_shutdown = True
                        self.shutdown_ec2_instance("Game server is empty.")

            time.sleep(self.config["heartbeat"])

    def shutdown_ec2_instance(self, reason):
        try:
            if self.game_monitor.server_running:
                self.game_monitor.shutdown_game_server()
                shutdown_timer = Timer(self.config["shutdown_wait_time"])
                while self.game_monitor.server_running and not shutdown_timer.expired:
                    time.sleep(self.config["heartbeat"])

                if self.game_monitor.server_running:
                    self.logger.error("Minecraft server did not shutdown properly!")
        except Exception as e:
            self.logger.error(f"Error shutting down game server: {e}")

        now_str = get_now_str()
        self.logger.info(f"{now_str}: Shutting down EC2 instance because: {reason}")

        # Shutdown the EC2 Instance after one minute
        if self.game_monitor.debug_mode:
            print("Server would shutdown here.")
            exit()
        else:
            os.system("shutdown -h 1")

