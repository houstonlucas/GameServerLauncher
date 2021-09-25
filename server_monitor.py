import os
import time
from datetime import datetime
from dateutil import tz

MAX_EMPTY_MINUTES = 15
MAX_EMPTY_SECONDS = MAX_EMPTY_MINUTES * 60

MAX_SERVER_DOWN_MINUTES = 15
MAX_SERVER_DOWN_SECONDS = MAX_SERVER_DOWN_MINUTES * 60

mc_sd_cmd = "tmux send-keys -t minecraft stop"
newline_cmd = "tmux send-keys -t minecraft C-m"
usr_cmd_format = 'runuser -l ec2-user -c "{}"'
minecraft_shutdown_cmd1 = usr_cmd_format.format(mc_sd_cmd)
minecraft_shutdown_cmd2 = usr_cmd_format.format(newline_cmd)

ec2_shutdown_cmd = "shutdown -h now"


def main():
    print("Monitor has started.")
    shutdown_reason = ""
    already_down = False
    should_shutdown = False
    while not should_shutdown:
        if is_server_running():
            already_down = False
            should_shutdown = monitor_server()
            if should_shutdown:
                shutdown_reason = "Empty MC Server"
        else:
            if not already_down:
                server_down_start = time.time()
                already_down = True
            else:
                down_time = time.time() - server_down_start
                if down_time > MAX_SERVER_DOWN_SECONDS:
                    should_shutdown = True
                    shutdown_reason = "No MC Server running"
        time.sleep(10)
    write_log(shutdown_reason)
    os.system(ec2_shutdown_cmd)


def write_log(shutdown_reason):
    shutdown_time_str = get_now_str()
    msg_str = "{}\nShutting down EC2 instance because: {}".format(
        shutdown_time_str, shutdown_reason
    )
    with open("monitor_log.txt", 'a+') as f:
        f.write(msg_str)
        f.write("\n")


def get_now_str():
    from_zone = tz.gettz("UTC")
    to_zone = tz.gettz("America/Los_Angeles")
    now_utc = datetime.utcnow().replace(tzinfo=from_zone)
    now = now_utc.astimezone(to_zone)
    shutdown_time_str = now.strftime("%Y/%m/%d %H:%M:%S")
    return shutdown_time_str


def monitor_server():
    # Returns True if the ec2 instance should be shutdown
    monitor_sleep_time = 10  # Seconds
    empty_server_start = time.time()
    already_empty = False
    should_shutdown = False

    while not should_shutdown and is_server_running():
        time.sleep(monitor_sleep_time)
        now = time.time()
        num_players_online = get_num_players_online()
        if num_players_online == 0:
            if not already_empty:
                empty_server_start = now
                already_empty = True
            else:
                idle_time = now - empty_server_start
                if idle_time > MAX_EMPTY_SECONDS:
                    should_shutdown = True
        else:
            already_empty = False

    if should_shutdown:
        print("Empty Server")
        os.system(minecraft_shutdown_cmd1)
        os.system(minecraft_shutdown_cmd2)
        # Wait for server to shutdown
        MAX_SECONDS_WAIT = 5 * 60
        wait_start = time.time()
        wait_time = time.time() - wait_start
        while is_server_running() and wait_time < MAX_SECONDS_WAIT:
            time.sleep(1)
            wait_time = time.time() - wait_start
        # TODO: Log if the server is still running when time limit is reached.
    return should_shutdown


def get_num_players_online():
    val = os.popen('lsof -iTCP:25565 -sTCP:ESTABLISHED').read()
    return val.count("ESTABLISHED")


def is_server_running():
    val = os.popen('lsof -iTCP:25565 -sTCP:LISTEN').read()
    return bool(val)


if __name__ == '__main__':
    main()
