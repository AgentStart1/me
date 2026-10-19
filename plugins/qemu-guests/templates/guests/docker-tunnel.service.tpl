[Unit]
Description=Guest Docker connection to Alpine backend
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/ssh {{TUNNEL_ARGS}}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
