#!/bin/bash

##############################################################################
# SaasOdoo - Docker Images Build Script
# Builds all required service images for docker-compose.ceph.yml deployment
##############################################################################

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root directory
PROJECT_ROOT="/root/saasodoo"
cd "$PROJECT_ROOT"

# Build counter
TOTAL_BUILDS=6
CURRENT_BUILD=0
START_TIME=$(date +%s)

##############################################################################
# Helper Functions
##############################################################################

print_header() {
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

print_step() {
    CURRENT_BUILD=$((CURRENT_BUILD + 1))
    echo ""
    echo -e "${YELLOW}[$CURRENT_BUILD/$TOTAL_BUILDS] $1${NC}"
    echo "------------------------------------------------------------"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

build_service() {
    local service_name=$1
    local image_name=$2
    local build_context=$3
    local dockerfile=${4:-Dockerfile}

    print_step "Building $service_name"

    if [ ! -f "$build_context/$dockerfile" ]; then
        print_error "Dockerfile not found at $build_context/$dockerfile"
        return 1
    fi

    echo "Building: $image_name"
    echo "Context: $build_context"
    echo "Dockerfile: $dockerfile"
    echo ""

    if docker build -t "$image_name" -f "$build_context/$dockerfile" "$build_context"; then
        print_success "$service_name built successfully"
        return 0
    else
        print_error "$service_name build failed"
        return 1
    fi
}

##############################################################################
# Main Build Process
##############################################################################

print_header "SaasOdoo Docker Images Build"
echo "Started at: $(date)"
echo ""

# Array to track failed builds
FAILED_BUILDS=()

##############################################################################
# 1. User Service
##############################################################################
if ! build_service "User Service" \
    "compose-user-service:latest" \
    "services/user-service"; then
    FAILED_BUILDS+=("user-service")
fi

##############################################################################
# 2. Instance Service
##############################################################################
if ! build_service "Instance Service" \
    "compose-instance-service:latest" \
    "services/instance-service"; then
    FAILED_BUILDS+=("instance-service")
fi

##############################################################################
# 3. Instance Worker (uses same Dockerfile as instance-service)
##############################################################################
if ! build_service "Instance Worker" \
    "compose-instance-worker:latest" \
    "services/instance-service"; then
    FAILED_BUILDS+=("instance-worker")
fi

##############################################################################
# 4. Billing Service
##############################################################################
if ! build_service "Billing Service" \
    "compose-billing-service:latest" \
    "services/billing-service"; then
    FAILED_BUILDS+=("billing-service")
fi

##############################################################################
# 5. Frontend Service
##############################################################################
if ! build_service "Frontend Service" \
    "compose-frontend-service:latest" \
    "services/frontend-service"; then
    FAILED_BUILDS+=("frontend-service")
fi

##############################################################################
# 6. Notification Service
##############################################################################
if ! build_service "Notification Service" \
    "compose-notification-service:latest" \
    "services/notification-service"; then
    FAILED_BUILDS+=("notification-service")
fi

##############################################################################
# Build Summary
##############################################################################

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

echo ""
print_header "Build Summary"

# Check if any builds failed
if [ ${#FAILED_BUILDS[@]} -eq 0 ]; then
    print_success "All $TOTAL_BUILDS images built successfully!"
    echo ""
    echo -e "${GREEN}Time taken: ${MINUTES}m ${SECONDS}s${NC}"
    echo ""

    # List built images
    echo "Built Images:"
    echo "------------------------------------------------------------"
    docker images | grep "compose-" | grep "latest"

    echo ""
    echo -e "${GREEN}✓ Ready for deployment!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Review/update .env file: nano infrastructure/compose/.env.swarm"
    echo "  2. Deploy the stack: docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo"
    echo ""

    exit 0
else
    print_error "${#FAILED_BUILDS[@]} build(s) failed!"
    echo ""
    echo "Failed builds:"
    for service in "${FAILED_BUILDS[@]}"; do
        echo "  - $service"
    done
    echo ""
    echo -e "${RED}Please fix the errors and run the script again.${NC}"
    echo ""
    exit 1
fi
