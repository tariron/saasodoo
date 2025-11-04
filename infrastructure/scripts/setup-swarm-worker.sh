#!/bin/bash
# =============================================================================
# Docker Swarm Worker Setup Script
# Run this on WORKER servers (server 2 and 3)
# =============================================================================

set -e

echo "========================================"
echo "Docker Swarm Worker Node Setup"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Update system
print_status "Updating system packages..."
apt-get update
apt-get upgrade -y

# Install prerequisites
print_status "Installing prerequisites..."
apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common

# Install Docker
print_status "Installing Docker..."
if ! command -v docker &> /dev/null; then
    # Add Docker's official GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # Set up the repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Install Docker Engine
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    print_status "Docker installed successfully"
else
    print_status "Docker is already installed"
fi

# Start and enable Docker
print_status "Starting Docker service..."
systemctl start docker
systemctl enable docker

# Add current user to docker group (if not root)
if [ -n "$SUDO_USER" ]; then
    print_status "Adding user $SUDO_USER to docker group..."
    usermod -aG docker $SUDO_USER
fi

# Verify Docker installation
print_status "Verifying Docker installation..."
docker --version

# Configure firewall (if ufw is active)
if systemctl is-active --quiet ufw; then
    print_status "Configuring firewall rules..."
    ufw allow 2377/tcp   # Swarm management
    ufw allow 7946/tcp   # Node communication
    ufw allow 7946/udp   # Node communication
    ufw allow 4789/udp   # Overlay network
    ufw reload
    print_status "Firewall configured"
fi

echo ""
print_status "=========================================="
print_status "Worker Node Docker Installation Complete!"
print_status "=========================================="
echo ""
print_warning "NEXT STEP: Join this node to the swarm"
echo ""
print_status "Run the JOIN COMMAND you received from the manager node:"
echo ""
print_warning "docker swarm join --token <WORKER-TOKEN> <MANAGER-IP>:2377"
echo ""
print_status "You should have received the join command from the manager node setup."
print_status "If you don't have it, run this on the MANAGER node:"
echo "  docker swarm join-token worker"
echo ""
