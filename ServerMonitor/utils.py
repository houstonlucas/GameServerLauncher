import os
import time
from datetime import datetime
from dateutil import tz


def create_tmux_session(session_name: str):
    usr_cmd_tmux_create_session = 'runuser -l houston -c "tmux new-session -d -s {}"'
    cmd = usr_cmd_tmux_create_session.format(session_name)
    os.system(cmd)


def tmux_sendkeys(session_name: str, command: str):
    """
    Runs 'command' in the tmux session with name 'session_name'
    """
    usr_cmd_tmux_send = 'runuser -l houston -c "tmux send-keys -t {} \'{}\'"'
    # Send command
    os.system(usr_cmd_tmux_send.format(session_name, command))
    # Send newline
    os.system(usr_cmd_tmux_send.format(session_name, "C-m"))


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
