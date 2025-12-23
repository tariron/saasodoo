#!/bin/bash
# =============================================================================
# Docker Swarm Manager Setup Script
# Run this on the FIRST server (manager node)
# =============================================================================

set -e

echo "========================================"
echo "Docker Swarm Manager Node Setup"
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

# Get the server's IP address
print_status "Detecting server IP address..."
SERVER_IP=$(hostname -I | awk '{print $1}')
echo "Detected IP: $SERVER_IP"
read -p "Is this correct? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    read -p "Enter the correct IP address: " SERVER_IP
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

# Initialize Docker Swarm
print_status "Initializing Docker Swarm as Manager..."
if docker info | grep -q "Swarm: active"; then
    print_warning "Docker Swarm is already initialized"
else
    docker swarm init --advertise-addr $SERVER_IP
    print_status "Docker Swarm initialized successfully"
fi

# Get join tokens
print_status "Generating join tokens..."
MANAGER_TOKEN=$(docker swarm join-token manager -q)
WORKER_TOKEN=$(docker swarm join-token worker -q)

# Create token file
TOKEN_FILE="/root/swarm-join-tokens.txt"
cat > $TOKEN_FILE <<EOF
=============================================================================
DOCKER SWARM JOIN TOKENS
=============================================================================
Manager IP: $SERVER_IP

MANAGER JOIN COMMAND (for additional manager nodes):
docker swarm join --token $MANAGER_TOKEN $SERVER_IP:2377

WORKER JOIN COMMAND (for worker nodes):
docker swarm join --token $WORKER_TOKEN $SERVER_IP:2377

=============================================================================
Run the appropriate command on your other servers
=============================================================================
EOF

print_status "Swarm join tokens saved to: $TOKEN_FILE"
cat $TOKEN_FILE

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

# Display node info
print_status "Displaying Swarm nodes..."
docker node ls

echo ""
print_status "=========================================="
print_status "Manager Node Setup Complete!"
print_status "=========================================="
echo ""
print_warning "IMPORTANT: Save the join tokens from $TOKEN_FILE"
print_warning "You will need them to add worker nodes"
echo ""
print_status "Next steps:"
echo "1. Run setup-swarm-worker.sh on your worker nodes"
echo "2. Use the WORKER JOIN COMMAND from the tokens file"
echo ""
