from abc import ABC, abstractmethod
import json
import logging
import os
import time
from datetime import datetime
from dateutil import tz


class GameMonitor(ABC):
    def __init__(self):
        pass

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
                        self.shutdown_ec2_instance("Game server seems to have crashed.")
            # If server is empty
            elif self.game_monitor.server_empty:
                if not self.empty_timer.is_running:
                    self.empty_timer.start()
                else:
                    if self.empty_timer.expired:
                        self.shutdown_ec2_instance("Game server is empty.")

            time.sleep(self.config["heartbeat"])

    def shutdown_ec2_instance(self, reason):
        try:
            if self.game_monitor.server_running:
                self.game_monitor.shutdown_game_server()
        except Exception as e:
            self.logger.error(f"Error shutting down game server: {e}")
        now_str = get_now_str()
        self.logger.info(f"{now_str}: Shutting down EC2 instance because: {reason}")
        # Shutdown the EC2 Instance after one minute
        os.system("shutdown -h 1")


class Timer:
    def __init__(self, max_time):
        self.start_time = None
        self.max_time = max_time

    @property
    def expired(self):
        if self.is_running:
            return self.elapsed >= self.max_time
        else:
            return False

    @property
    def is_running(self):
        return self.start_time is not None

    @property
    def elapsed(self):
        if self.is_running:
            return time.time() - self.start_time

    def start(self):
        self.start_time = time.time()

    def reset(self):
        self.start_time = None


def get_now_str():
    from_zone = tz.gettz("UTC")
    to_zone = tz.gettz("America/Los_Angeles")
    now_utc = datetime.utcnow().replace(tzinfo=from_zone)
    now = now_utc.astimezone(to_zone)
    now_str = now.strftime("%Y/%m/%d %H:%M:%S")
    return now_str
