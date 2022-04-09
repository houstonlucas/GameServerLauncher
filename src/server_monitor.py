import threading
from abc import ABC, abstractmethod
import json
import logging
import os
import time
from pathlib import Path

from typing import List, Union

from src.constants import REQUEST_PATH, RESPONSE_PATH, CONFIRM_PATH
from src.utils import get_now_str, Timer, json_from_file, json_to_file


class GameMonitor(ABC):
    def __init__(self, debug_mode):
        self.debug_mode = debug_mode

    # TODO: Add in mocked base logger
    def parse_command(self, command: str):
        command_words = command.split()
        custom_command_parsed, custom_command_message = self.parse_custom_commands(command_words)

        if custom_command_parsed:
            return custom_command_message
        elif "start" in command_words:
            if self.server_running:
                return "Server started successfully."
            else:
                return "Error: server did not start successfully."
        elif "stop" in command_words:
            self.shutdown_game_server()
            return "Server has shutdown."
        elif "echo" in command_words:
            return command
        else:
            return 'Command not recognized.'

    def parse_custom_commands(self, command_words: List[str]):
        """Parse any custom commands besides the base commands.

        Returns:
            A tuple of whether there was a command that fit, and the response to return
            """
        return False, ""

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

    def __init__(self, game_monitor: GameMonitor, config_file: Union[str, Path]):
        self.config = json_from_file(config_file)

        self.logger = logging.getLogger("EC2Monitor")
        logging_level = logging.getLevelName(self.config["loggingLevel"])
        self.logger.setLevel(logging_level)
        self.logger.addHandler(
            logging.FileHandler(self.config['log_file'])
        )

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
            self.logger.debug(f"Server would shutdown here. {get_now_str()}")
        else:
            self.logger.debug(f"Server shutdown initiated. {get_now_str()}")
            logging.shutdown()
            os.system("shutdown -h 1")

    def start_game_server(self):
        # Start game server
        self.logger.debug(f"Attempting to start game server. {get_now_str()}")
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
        self.logger.debug(f"Game server started. {get_now_str()}")

    def check_for_crashed_server(self):
        # If server isn't running
        if not self.game_monitor.server_running:
            # Evaluated if server has been down long enough to shutdown
            if not self.down_timer.is_running:
                # Start timer to trigger shutdown.
                self.down_timer.start()
                self.logger.warning(f"Down server detected: {get_now_str()}")
            else:
                # Check expiration of timer, shutdown if expired.
                if self.down_timer.expired:
                    self.should_shutdown = True
                    self.shutdown_ec2_instance("Game server seems to have crashed.")
        # Server is running
        else:
            if self.down_timer.is_running:
                # Log if timer was previously running.
                self.logger.debug(f"Server is back up. {get_now_str()}")
            self.down_timer.reset()

    def check_for_empty_server(self):
        # If server is empty
        if self.game_monitor.server_empty:
            if not self.empty_timer.is_running:
                # Start timer to trigger shutdown.
                self.empty_timer.start()
                self.logger.warning(f"Empty server detected: {get_now_str()}")
            else:
                # Check expiration of timer, shutdown if expired.
                if self.empty_timer.expired:
                    self.should_shutdown = True
                    self.shutdown_ec2_instance("Game server is empty.")
        # Server isn't empty
        else:
            if self.empty_timer.is_running:
                # Log if timer was previously running.
                self.logger.debug(f"Game server no longer empty. {get_now_str()}")
            self.empty_timer.reset()

    def check_for_incoming_message(self):
        # Poll for incoming messages stored in the request json file
        if os.path.exists(REQUEST_PATH):
            # Read and immediately delete the request
            json_request = json_from_file(REQUEST_PATH)
            os.remove(REQUEST_PATH)

            # Create and store response in the response json file
            response = self.handle_request(json_request['message'])
            json_response = {'message': response}
            json_to_file(json_response, RESPONSE_PATH)

            # Poll for confirmation that response was received
            confirm_timer = Timer(self.config['command_timeout'])
            confirm_timer.start()
            confirmation = False
            while not confirm_timer.expired:
                if os.path.exists(CONFIRM_PATH):
                    # Confirmation received
                    confirmation = True

            if not confirmation:
                self.logger.warning('No confirmation received')

            # Clean out the files
            if os.path.exists(RESPONSE_PATH):
                os.remove(RESPONSE_PATH)
            if os.path.exists(CONFIRM_PATH):
                os.remove(CONFIRM_PATH)

    def handle_request(self, data: str) -> str:
        response = self.game_monitor.parse_command(data)
        return response
