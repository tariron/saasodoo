#!/bin/bash

# Build and Push Images to Kubernetes Registry
# This script builds all service images and pushes them to registry.62.171.153.219.nip.io

set -e

REGISTRY="registry.62.171.153.219.nip.io"
PROJECT_ROOT="/root/Projects/saasodoo"

echo "============================================"
echo "Building and Pushing Images to $REGISTRY"
echo "============================================"

# Function to build and push an image
build_and_push() {
    local service_name=$1
    local dockerfile_path=$2
    local context_path=$3

    echo ""
    echo "Building $service_name..."
    docker build -t $REGISTRY/$service_name:latest -f $dockerfile_path $context_path

    echo "Pushing $service_name to registry..."
    docker push $REGISTRY/$service_name:latest

    echo "✓ $service_name completed"
}

# Build PostgreSQL image
echo ""
echo "=== Building Infrastructure Images ==="
build_and_push "postgres" \
    "$PROJECT_ROOT/infrastructure/images/postgres/Dockerfile" \
    "$PROJECT_ROOT/infrastructure/images/postgres"

# Build Redis image
build_and_push "redis" \
    "$PROJECT_ROOT/infrastructure/images/redis/Dockerfile" \
    "$PROJECT_ROOT/infrastructure/images/redis"

# Build service images
echo ""
echo "=== Building Service Images ==="

build_and_push "user-service" \
    "$PROJECT_ROOT/services/user-service/Dockerfile" \
    "$PROJECT_ROOT"

build_and_push "billing-service" \
    "$PROJECT_ROOT/services/billing-service/Dockerfile" \
    "$PROJECT_ROOT"

build_and_push "instance-service" \
    "$PROJECT_ROOT/services/instance-service/Dockerfile" \
    "$PROJECT_ROOT"

build_and_push "database-service" \
    "$PROJECT_ROOT/services/database-service/Dockerfile" \
    "$PROJECT_ROOT"

build_and_push "notification-service" \
    "$PROJECT_ROOT/services/notification-service/Dockerfile" \
    "$PROJECT_ROOT"

build_and_push "frontend-service" \
    "$PROJECT_ROOT/services/frontend-service/Dockerfile" \
    "$PROJECT_ROOT/services/frontend-service"

echo ""
echo "============================================"
echo "✓ All images built and pushed successfully!"
echo "============================================"
echo ""
echo "View registry catalog:"
echo "  curl http://registry.62.171.153.219.nip.io/v2/_catalog"
