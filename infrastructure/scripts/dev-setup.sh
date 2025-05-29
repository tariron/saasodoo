#!/bin/bash

# SaaSOdoo Development Environment Setup Script
# This script sets up the complete development environment

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running on Windows
is_windows() {
    case "$(uname -s)" in
        CYGWIN*|MINGW32*|MINGW64*|MSYS*) return 0 ;;
        *) return 1 ;;
    esac
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check Docker and Docker Compose
check_docker() {
    log_info "Checking Docker installation..."
    
    if ! command_exists docker; then
        log_error "Docker is not installed. Please install Docker Desktop."
        exit 1
    fi
    
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker daemon is not running. Please start Docker Desktop."
        exit 1
    fi
    
    if ! command_exists docker-compose && ! docker compose version >/dev/null 2>&1; then
        log_error "Docker Compose is not available. Please install Docker Compose."
        exit 1
    fi
    
    log_success "Docker is installed and running"
}

# Function to create .env file from .env.example
setup_env_file() {
    log_info "Setting up environment variables..."
    
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            cp .env.example .env
            log_success "Created .env file from .env.example"
            log_warning "Please review and update the .env file with your specific settings"
        else
            log_error ".env.example file not found"
            exit 1
        fi
    else
        log_info ".env file already exists"
    fi
}

# Function to create necessary directories
create_directories() {
    log_info "Creating necessary directories..."
    
    directories=(
        "data/postgres"
        "data/redis"
        "data/rabbitmq"
        "data/elasticsearch"
        "data/prometheus"
        "data/grafana"
        "data/minio"
        "logs/services"
        "logs/infrastructure"
        "shared/configs/postgres"
        "infrastructure/monitoring/grafana/dashboards"
        "infrastructure/monitoring/grafana/datasources"
        "infrastructure/monitoring/rules"
        "ssl/certificates"
    )
    
    for dir in "${directories[@]}"; do
        mkdir -p "$dir"
        log_info "Created directory: $dir"
    done
    
    log_success "All directories created"
}

# Function to setup PostgreSQL init scripts
setup_postgres_init() {
    log_info "Setting up PostgreSQL initialization scripts..."
    
    cat > shared/configs/postgres/01-init-databases.sql << 'EOF'
-- Create databases for each microservice
CREATE DATABASE auth;
CREATE DATABASE billing;
CREATE DATABASE tenant;
CREATE DATABASE communication;
CREATE DATABASE analytics;

-- Create users for each service (using environment variables when possible)
CREATE USER auth_user WITH PASSWORD 'auth_pass';
CREATE USER billing_user WITH PASSWORD 'billing_pass';
CREATE USER tenant_user WITH PASSWORD 'tenant_pass';
CREATE USER communication_user WITH PASSWORD 'communication_pass';
CREATE USER analytics_user WITH PASSWORD 'analytics_pass';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE auth TO auth_user;
GRANT ALL PRIVILEGES ON DATABASE billing TO billing_user;
GRANT ALL PRIVILEGES ON DATABASE tenant TO tenant_user;
GRANT ALL PRIVILEGES ON DATABASE communication TO communication_user;
GRANT ALL PRIVILEGES ON DATABASE analytics TO analytics_user;

-- Create extensions
\c auth;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

\c billing;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

\c tenant;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

\c communication;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

\c analytics;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
EOF

    log_success "PostgreSQL initialization scripts created"
}

# Function to setup Grafana datasources
setup_grafana_datasources() {
    log_info "Setting up Grafana datasources..."
    
    cat > infrastructure/monitoring/grafana/datasources/prometheus.yml << 'EOF'
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
    jsonData:
      httpMethod: POST
      prometheusType: Prometheus
      prometheusVersion: 2.40.0
      cacheLevel: 'High'
      disableMetricsLookup: false
      incrementalQuerying: false
      intervalFactor: 2
      
  - name: Elasticsearch
    type: elasticsearch
    access: proxy
    url: http://elasticsearch:9200
    database: "logstash-*"
    jsonData:
      esVersion: "8.8.0"
      timeField: "@timestamp"
      interval: Daily
      maxConcurrentShardRequests: 5
      logMessageField: message
      logLevelField: level
EOF

    log_success "Grafana datasources configured"
}

# Function to setup local DNS entries
setup_local_dns() {
    log_info "Setting up local DNS entries..."
    
    if is_windows; then
        hosts_file="/c/Windows/System32/drivers/etc/hosts"
    else
        hosts_file="/etc/hosts"
    fi
    
    # Check if entries already exist
    if grep -q "saasodoo.local" "$hosts_file" 2>/dev/null; then
        log_info "Local DNS entries already exist"
        return
    fi
    
    # DNS entries to add
    dns_entries=(
        "127.0.0.1 saasodoo.local"
        "127.0.0.1 app.saasodoo.local"
        "127.0.0.1 admin.saasodoo.local"
        "127.0.0.1 api.saasodoo.local"
        "127.0.0.1 traefik.saasodoo.local"
        "127.0.0.1 prometheus.saasodoo.local"
        "127.0.0.1 grafana.saasodoo.local"
        "127.0.0.1 kibana.saasodoo.local"
        "127.0.0.1 rabbitmq.saasodoo.local"
        "127.0.0.1 mail.saasodoo.local"
        "127.0.0.1 minio.saasodoo.local"
        "127.0.0.1 s3.saasodoo.local"
    )
    
    log_warning "To add local DNS entries, you may need administrator/sudo privileges"
    log_info "You can add these entries manually to $hosts_file:"
    
    for entry in "${dns_entries[@]}"; do
        echo "  $entry"
    done
    
    # Try to add automatically (may require sudo)
    if command_exists sudo && [ "$hosts_file" = "/etc/hosts" ]; then
        read -p "Do you want to add DNS entries automatically? (requires sudo) [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            for entry in "${dns_entries[@]}"; do
                echo "$entry" | sudo tee -a "$hosts_file" >/dev/null
            done
            log_success "DNS entries added to hosts file"
        fi
    fi
}

# Function to pull required Docker images
pull_docker_images() {
    log_info "Pulling required Docker images..."
    
    images=(
        "traefik:v3.0"
        "postgres:15-alpine"
        "redis:7-alpine"
        "rabbitmq:3-management-alpine"
        "prom/prometheus:latest"
        "grafana/grafana:latest"
        "docker.elastic.co/elasticsearch/elasticsearch:8.8.0"
        "docker.elastic.co/kibana/kibana:8.8.0"
        "mailhog/mailhog:latest"
        "minio/minio:latest"
    )
    
    for image in "${images[@]}"; do
        log_info "Pulling $image..."
        docker pull "$image" || log_warning "Failed to pull $image"
    done
    
    log_success "Docker images pulled"
}

# Function to initialize Docker network
setup_docker_network() {
    log_info "Setting up Docker network..."
    
    if ! docker network ls | grep -q "saasodoo-network"; then
        docker network create saasodoo-network
        log_success "Created saasodoo-network"
    else
        log_info "saasodoo-network already exists"
    fi
}

# Function to validate setup
validate_setup() {
    log_info "Validating setup..."
    
    # Check if all required files exist
    required_files=(
        ".env"
        "infrastructure/compose/docker-compose.dev.yml"
        "infrastructure/traefik/traefik.yml"
        "infrastructure/monitoring/prometheus.yml"
        "Makefile"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            log_error "Required file missing: $file"
            exit 1
        fi
    done
    
    log_success "All required files are present"
}

# Main setup function
main() {
    log_info "Starting SaaSOdoo development environment setup..."
    
    # Change to script directory
    cd "$(dirname "$0")/../.."
    
    # Run setup steps
    check_docker
    setup_env_file
    create_directories
    setup_postgres_init
    setup_grafana_datasources
    setup_docker_network
    pull_docker_images
    setup_local_dns
    validate_setup
    
    log_success "Development environment setup completed!"
    echo
    log_info "Next steps:"
    echo "  1. Review and update the .env file with your settings"
    echo "  2. Run 'make dev-up' to start the development environment"
    echo "  3. Access the services at:"
    echo "     - Traefik Dashboard: http://traefik.saasodoo.local:8080"
    echo "     - Grafana: http://grafana.saasodoo.local"
    echo "     - Prometheus: http://prometheus.saasodoo.local"
    echo "     - RabbitMQ: http://rabbitmq.saasodoo.local"
    echo "     - MailHog: http://mail.saasodoo.local"
    echo "     - MinIO: http://minio.saasodoo.local"
}

# Run main function
main "$@" 