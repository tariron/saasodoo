#!/bin/bash

# SaaSOdoo - Build Individual Service Script
# Usage: ./scripts/build-service.sh <service-name> [--no-cache]

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Load environment variables
ENV_FILE="infrastructure/compose/.env.swarm"
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

# Check if service name provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: Service name required${NC}"
    echo ""
    echo "Usage: $0 <service-name> [--no-cache]"
    echo ""
    echo "Available services:"
    echo "  Infrastructure:"
    echo "    - postgres"
    echo "    - redis"
    echo ""
    echo "  Application Services:"
    echo "    - user-service"
    echo "    - instance-service"
    echo "    - instance-worker"
    echo "    - billing-service"
    echo "    - notification-service"
    echo "    - frontend-service"
    echo ""
    echo "Example: $0 user-service"
    echo "Example: $0 postgres --no-cache"
    exit 1
fi

SERVICE_NAME=$1
NO_CACHE=""

if [ "$2" == "--no-cache" ]; then
    NO_CACHE="--no-cache"
    echo -e "${YELLOW}Building with --no-cache flag${NC}"
fi

# Define service configurations
declare -A DOCKERFILES
declare -A BUILD_CONTEXTS

# Infrastructure services
DOCKERFILES[postgres]="infrastructure/postgres/Dockerfile"
BUILD_CONTEXTS[postgres]="."

DOCKERFILES[redis]="infrastructure/redis/Dockerfile"
BUILD_CONTEXTS[redis]="."

# Application services
DOCKERFILES[user-service]="services/user-service/Dockerfile"
BUILD_CONTEXTS[user-service]="services/user-service/"

DOCKERFILES[instance-service]="services/instance-service/Dockerfile"
BUILD_CONTEXTS[instance-service]="services/instance-service/"

DOCKERFILES[instance-worker]="services/instance-service/Dockerfile"
BUILD_CONTEXTS[instance-worker]="services/instance-service/"

DOCKERFILES[billing-service]="services/billing-service/Dockerfile"
BUILD_CONTEXTS[billing-service]="services/billing-service/"

DOCKERFILES[notification-service]="services/notification-service/Dockerfile"
BUILD_CONTEXTS[notification-service]="services/notification-service/"

DOCKERFILES[frontend-service]="services/frontend-service/Dockerfile"
BUILD_CONTEXTS[frontend-service]="services/frontend-service/"

# Check if service exists
if [ -z "${DOCKERFILES[$SERVICE_NAME]}" ]; then
    echo -e "${RED}Error: Unknown service '${SERVICE_NAME}'${NC}"
    echo ""
    echo "Run '$0' without arguments to see available services"
    exit 1
fi

DOCKERFILE_PATH="${DOCKERFILES[$SERVICE_NAME]}"
BUILD_CONTEXT="${BUILD_CONTEXTS[$SERVICE_NAME]}"
IMAGE_TAG="${REGISTRY}/compose-${SERVICE_NAME}:latest"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Building ${SERVICE_NAME}${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Dockerfile:     ${DOCKERFILE_PATH}"
echo -e "Build Context:  ${BUILD_CONTEXT}"
echo -e "Image Tag:      ${IMAGE_TAG}"
echo ""

# Build the image
echo -e "${YELLOW}Building ${SERVICE_NAME}...${NC}"
if docker build ${NO_CACHE} -t ${IMAGE_TAG} -f ${DOCKERFILE_PATH} ${BUILD_CONTEXT}; then
    echo -e "${GREEN}✓ Built ${SERVICE_NAME}${NC}"
    echo ""

    # Push to registry
    echo -e "${YELLOW}Pushing ${SERVICE_NAME} to registry...${NC}"
    if docker push ${IMAGE_TAG}; then
        echo -e "${GREEN}✓ Pushed ${SERVICE_NAME}${NC}"
        echo ""

        # Show deployment instructions
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}  Build Complete!${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""
        echo -e "${YELLOW}To update the service in Docker Swarm:${NC}"
        echo -e "  docker service update --image ${IMAGE_TAG} saasodoo_${SERVICE_NAME}"
        echo ""
        echo -e "${YELLOW}Or redeploy the entire stack:${NC}"
        echo -e "  set -a && source infrastructure/compose/.env.swarm && set +a && docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo"
        echo ""
    else
        echo -e "${RED}✗ Failed to push ${SERVICE_NAME}${NC}"
        exit 1
    fi
else
    echo -e "${RED}✗ Failed to build ${SERVICE_NAME}${NC}"
    exit 1
fi
