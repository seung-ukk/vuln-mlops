#!/bin/bash
set -euo pipefail

# Intentionally vulnerable, disposable escape-worker hook for the lab. The
# Git-controlled workload can initially only read this exact directory.
install -d -m 0700 -o root -g root /var/lib/vuln-mlops/maintenance
install -d -m 0700 -o root -g root /var/lib/vuln-mlops/node-evidence
printf '#!/bin/bash\nexit 0\n' > /var/lib/vuln-mlops/maintenance/task.sh
chmod 0600 /var/lib/vuln-mlops/maintenance/task.sh

cat > /etc/systemd/system/vuln-mlops-maintenance.service <<'UNIT'
[Unit]
Description=Disposable vuln-mlops host maintenance task

[Service]
Type=oneshot
User=root
Group=root
ExecStart=/usr/bin/bash /var/lib/vuln-mlops/maintenance/task.sh
StandardOutput=journal
StandardError=journal
UNIT

cat > /etc/systemd/system/vuln-mlops-maintenance.path <<'UNIT'
[Unit]
Description=Watch the disposable vuln-mlops maintenance task

[Path]
PathChanged=/var/lib/vuln-mlops/maintenance/task.sh
Unit=vuln-mlops-maintenance.service

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now vuln-mlops-maintenance.path
