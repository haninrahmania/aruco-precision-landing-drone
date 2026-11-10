#!/bin/bash
# Makes precland.py start automatically every time the Pi boots.
# Run once, from inside the precland folder:   bash install_service.sh
# Extra options for precland.py can be passed, e.g.:   bash install_service.sh --flip-y
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
EXTRA="$*"

sudo tee /etc/systemd/system/precland.service > /dev/null <<EOF
[Unit]
Description=ArUco precision landing companion
After=multi-user.target

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=/usr/bin/python3 -u $DIR/precland.py --wifi-off-when-armed $EXTRA
Restart=always
RestartSec=3
User=root
StandardOutput=append:$DIR/precland.log
StandardError=append:$DIR/precland.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable precland.service
sudo systemctl restart precland.service
echo "Installed. precland now starts at every boot."
echo "  Status:      sudo systemctl status precland"
echo "  Live log:    tail -f $DIR/precland.log"
echo "  Stop it:     sudo systemctl stop precland     (e.g. before running it by hand)"
echo "  Remove it:   sudo systemctl disable --now precland"
