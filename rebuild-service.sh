#!/bin/bash

##############################################################################
# SaasOdoo - Individual Service Rebuild Script
# Quickly rebuild a single service image
##############################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_ROOT="/root/saasodoo"
cd "$PROJECT_ROOT"

##############################################################################
# Service Configuration
##############################################################################

declare -A SERVICES
SERVICES[user]="compose-user-service:latest|services/user-service"
SERVICES[instance]="compose-instance-service:latest|services/instance-service"
SERVICES[worker]="compose-instance-worker:latest|services/instance-service"
SERVICES[billing]="compose-billing-service:latest|services/billing-service"
SERVICES[frontend]="compose-frontend-service:latest|services/frontend-service"
SERVICES[notification]="compose-notification-service:latest|services/notification-service"

##############################################################################
# Usage
##############################################################################

usage() {
    echo -e "${BLUE}Usage:${NC} $0 <service-name>"
    echo ""
    echo "Available services:"
    echo "  user         - User/Auth Service"
    echo "  instance     - Instance Service"
    echo "  worker       - Instance Worker (Celery)"
    echo "  billing      - Billing Service"
    echo "  frontend     - Frontend Service"
    echo "  notification - Notification Service"
    echo ""
    echo "Examples:"
    echo "  $0 user"
    echo "  $0 instance"
    echo "  $0 billing"
    exit 1
}

##############################################################################
# Main
##############################################################################

if [ $# -eq 0 ]; then
    echo -e "${RED}Error: No service specified${NC}"
    echo ""
    usage
fi

SERVICE_KEY=$1

if [ -z "${SERVICES[$SERVICE_KEY]}" ]; then
    echo -e "${RED}Error: Unknown service '$SERVICE_KEY'${NC}"
    echo ""
    usage
fi

# Parse service configuration
IFS='|' read -r IMAGE_NAME BUILD_CONTEXT <<< "${SERVICES[$SERVICE_KEY]}"

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}Rebuilding: $SERVICE_KEY${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""
echo "Image:   $IMAGE_NAME"
echo "Context: $BUILD_CONTEXT"
echo ""

START_TIME=$(date +%s)

if docker build -t "$IMAGE_NAME" "$BUILD_CONTEXT"; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo -e "${GREEN}✓ Build successful! (${DURATION}s)${NC}"
    echo ""
    echo "Image details:"
    docker images "$IMAGE_NAME"
    echo ""

    # Offer to restart service if it's running
    STACK_NAME="saasodoo"
    SERVICE_NAME="saasodoo_${SERVICE_KEY}-service"

    if docker service ls --format '{{.Name}}' | grep -q "$SERVICE_NAME" 2>/dev/null; then
        echo -e "${YELLOW}Service is running in stack.${NC}"
        echo "To update running service:"
        echo "  docker service update --force ${SERVICE_NAME}"
        echo ""
    fi

    exit 0
else
    echo ""
    echo -e "${RED}✗ Build failed${NC}"
    exit 1
fi
