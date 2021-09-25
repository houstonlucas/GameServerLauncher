cd /home/ec2-user/
tmux new-session -d -s minecraft
tmux new-session -d -s monitor
tmux send-keys -t minecraft "./start_server.sh"
tmux send-keys -t minecraft C-m
tmux send-keys -t monitor "sudo python server_monitor.py"
tmux send-keys -t monitor C-m
