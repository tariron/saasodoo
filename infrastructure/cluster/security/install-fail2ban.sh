#!/bin/bash
# Fail2ban Installation and Configuration Script
# This script installs and configures fail2ban to protect against brute-force attacks

set -e

echo "================================================"
echo "Fail2ban Installation and Configuration"
echo "================================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root"
    echo "Please run: sudo bash $0"
    exit 1
fi

echo "[1/5] Updating package lists..."
apt update

echo "[2/5] Installing fail2ban..."
apt install -y fail2ban

echo "[3/5] Enabling fail2ban service..."
systemctl enable fail2ban

echo "[4/5] Creating fail2ban configuration..."

# Create local configuration file
cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
# Ban hosts for 1 hour (3600 seconds)
bantime = 3600

# A host is banned if it has generated "maxretry" during the last "findtime"
findtime = 600

# Number of failures before a host gets banned
maxretry = 5

# Destination email for ban notifications (optional)
# destemail = your-email@example.com

# Sender email
# sender = fail2ban@example.com

# Email action (optional - requires mail setup)
# action = %(action_mwl)s

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 5
bantime = 3600
findtime = 600

# Optional: Protect other services
# [nginx-http-auth]
# enabled = true
# port = http,https
# logpath = /var/log/nginx/error.log

# [docker-auth]
# enabled = true
# filter = docker-auth
# logpath = /var/log/docker.log
# maxretry = 5
EOF

echo "[5/5] Starting fail2ban..."
systemctl start fail2ban

echo ""
echo "================================================"
echo "Fail2ban Installation Complete!"
echo "================================================"
echo ""
echo "Status:"
systemctl status fail2ban --no-pager
echo ""
echo "Configuration:"
echo "  - Max retries: 5 failed attempts"
echo "  - Ban time: 1 hour (3600 seconds)"
echo "  - Find time: 10 minutes (600 seconds)"
echo ""
echo "Useful commands:"
echo "  - Check status: systemctl status fail2ban"
echo "  - View banned IPs: fail2ban-client status sshd"
echo "  - Unban an IP: fail2ban-client set sshd unbanip <IP>"
echo "  - View logs: tail -f /var/log/fail2ban.log"
echo ""
