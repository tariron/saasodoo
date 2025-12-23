#!/bin/bash

# SaaSOdoo - Build All Services Script
# This script builds all custom Docker images and pushes them to the local registry

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Load environment variables
ENV_FILE="infrastructure/orchestration/swarm/.env.swarm"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: Environment file not found: $ENV_FILE${NC}"
    exit 1
fi

# Source the environment file and expand variables
set -a
source "$ENV_FILE"
set +a

# Expand DOCKER_REGISTRY variable (in case it contains ${BASE_DOMAIN})
REGISTRY=$(eval echo "$DOCKER_REGISTRY")

if [ -z "$REGISTRY" ]; then
    echo -e "${RED}Error: DOCKER_REGISTRY not set in $ENV_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}Using registry: ${REGISTRY}${NC}"
echo ""

# Flag for no-cache builds
NO_CACHE=""
if [ "$1" == "--no-cache" ]; then
    NO_CACHE="--no-cache"
    echo -e "${YELLOW}Building with --no-cache flag${NC}"
fi

# Function to build and push an image
build_and_push() {
    local service_name=$1
    local dockerfile_path=$2
    local build_context=$3
    local image_tag="${REGISTRY}/compose-${service_name}:latest"

    echo -e "${YELLOW}Building ${service_name}...${NC}"
    if docker build ${NO_CACHE} -t ${image_tag} -f ${dockerfile_path} ${build_context}; then
        echo -e "${GREEN}✓ Built ${service_name}${NC}"

        echo -e "${YELLOW}Pushing ${service_name} to registry...${NC}"
        if docker push ${image_tag}; then
            echo -e "${GREEN}✓ Pushed ${service_name}${NC}"
        else
            echo -e "${RED}✗ Failed to push ${service_name}${NC}"
            return 1
        fi
    else
        echo -e "${RED}✗ Failed to build ${service_name}${NC}"
        return 1
    fi
    echo ""
}

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  SaaSOdoo - Build All Services${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Build infrastructure services
echo -e "${YELLOW}Building Infrastructure Services...${NC}"
echo ""

build_and_push "postgres" "infrastructure/images/postgres/Dockerfile" "."
build_and_push "redis" "infrastructure/images/redis/Dockerfile" "."

echo ""
echo -e "${YELLOW}Building Application Services...${NC}"
echo ""

# Build application services (use root context for access to shared/)
build_and_push "user-service" "services/user-service/Dockerfile" "."
build_and_push "instance-service" "services/instance-service/Dockerfile" "."
build_and_push "instance-worker" "services/instance-service/Dockerfile" "."
build_and_push "billing-service" "services/billing-service/Dockerfile" "."
build_and_push "notification-service" "services/notification-service/Dockerfile" "."
build_and_push "frontend-service" "services/frontend-service/Dockerfile" "."

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Build Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}To deploy the updated services, run:${NC}"
echo -e "  set -a && source infrastructure/orchestration/swarm/.env.swarm && set +a && docker stack deploy -c infrastructure/orchestration/swarm/docker-compose.ceph.yml saasodoo"
echo ""
