import threading
from abc import ABC, abstractmethod
import json
import logging
import os
import time

from typing import Type

from src.utils import get_now_str, Timer


class GameMonitor(ABC):
    def __init__(self, debug_mode):
        self.debug_mode = debug_mode

    @abstractmethod
    def parse_command(self, command: str):
        raise NotImplementedError

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

        self.logger = logging.getLogger("EC2Monitor")
        logging_level = logging.getLevelName(self.config["loggingLevel"])
        self.logger.setLevel(logging_level)

        self.should_shutdown = False
        self.empty_timer = Timer(self.config["max_empty_time"])
        self.down_timer = Timer(self.config["max_downtime"])

        self.game_monitor = game_monitor

    def run(self):
        self.start_game_server()

        # Don't start if game server failed to start.
        if self.should_shutdown:
            return

        self.monitor_game()

    def monitor_game(self):
        self.start_game_server()
        # Monitor for shutdown conditions
        while not self.should_shutdown:
            self.check_for_crashed_server()
            self.check_for_empty_server()
            self.check_for_incoming_message()

            time.sleep(self.config["heartbeat"])

    def shutdown_ec2_instance(self, reason):
        self.should_shutdown = True
        try:
            if self.game_monitor.server_running:
                self.game_monitor.shutdown_game_server()
                shutdown_timer = Timer(self.config["shutdown_wait_time"])
                while self.game_monitor.server_running and not shutdown_timer.expired:
                    time.sleep(self.config["heartbeat"])

                if self.game_monitor.server_running:
                    self.logger.error("Game server did not shutdown properly!")
        except Exception as e:
            self.logger.error(f"Error shutting down game server: {e}")

        now_str = get_now_str()
        self.logger.error(f"{now_str}: Shutting down EC2 instance because: {reason}")

        # Shutdown the EC2 Instance after one minute
        if self.game_monitor.debug_mode:
            print("Server would shutdown here.")
        else:
            os.system("shutdown -h 1")

    def start_game_server(self):
        # Start game server
        self.logger.debug("Attempting to start game server.")
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
        self.logger.debug("Game server started.")

    def check_for_crashed_server(self):
        # If server isn't running
        if not self.game_monitor.server_running:
            # Evaluated if server has been down long enough to shutdown
            if not self.down_timer.is_running:
                self.down_timer.start()
                self.logger.warning(f"Down server detected: {get_now_str()}")
            else:
                if self.down_timer.expired:
                    self.should_shutdown = True
                    self.shutdown_ec2_instance("Game server seems to have crashed.")
        else:
            self.down_timer.reset()

    def check_for_empty_server(self):
        # If server is empty
        if self.game_monitor.server_empty:
            if not self.empty_timer.is_running:
                self.empty_timer.start()
                self.logger.warning(f"Empty server detected: {get_now_str()}")
            else:
                if self.empty_timer.expired:
                    self.should_shutdown = True
                    self.shutdown_ec2_instance("Game server is empty.")
        else:
            self.empty_timer.reset()

    def check_for_incoming_message(self):
        # Incoming messages are stored in a json file.
        if os.path.exists(self.config['request_path']):
            with open(self.config['request_path']) as request_file:
                json_request = json.load(request_file)

            # Delete message to not parse it multiple times
            os.remove(self.config['request_path'])

            response = self.handle_request(json_request['message'])
            json_response = {'message': response}
            with open(self.config['response_path']) as response_file:
                json.dump(json_response, response_file)

            # Wait a while for confirmation that response was received
            confirm_timer = Timer(self.config['command_timeout'])
            confirm_timer.start()
            while not confirm_timer.expired:
                if os.path.exists(self.config['confirmation_path']):
                    # Confirmation received
                    os.remove(self.config['response_path'])
                    os.remove(self.config['confirmation_path'])
                    confirm_timer.reset()

            if confirm_timer.is_running:
                self.logger.warning('No confirmation received')

    def handle_request(self, data: str) -> str:
        response = self.game_monitor.parse_command(data)
        return response
