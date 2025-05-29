#!/bin/bash

# SaaSOdoo Build All Services Script
# This script builds all Docker images for the SaaSOdoo platform

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REGISTRY="${DOCKER_REGISTRY:-saasodoo}"
TAG="${BUILD_TAG:-latest}"
BUILD_PARALLEL="${BUILD_PARALLEL:-true}"
PUSH_IMAGES="${PUSH_IMAGES:-false}"
CACHE_FROM="${CACHE_FROM:-true}"

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

# Function to check if Docker is available
check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker daemon is not running"
        exit 1
    fi
    
    log_success "Docker is available"
}

# Function to check if BuildKit is available
check_buildkit() {
    if docker buildx version >/dev/null 2>&1; then
        export DOCKER_BUILDKIT=1
        log_success "BuildKit is available"
        return 0
    else
        log_warning "BuildKit not available, using legacy builder"
        return 1
    fi
}

# Function to build a single service
build_service() {
    local service_name="$1"
    local service_path="$2"
    local dockerfile="${3:-Dockerfile}"
    
    log_info "Building $service_name..."
    
    if [ ! -d "$service_path" ]; then
        log_warning "Service directory not found: $service_path (skipping)"
        return 0
    fi
    
    if [ ! -f "$service_path/$dockerfile" ]; then
        log_warning "Dockerfile not found: $service_path/$dockerfile (skipping)"
        return 0
    fi
    
    local image_name="$REGISTRY/$service_name:$TAG"
    local build_args=""
    
    # Add cache from arguments if enabled
    if [ "$CACHE_FROM" = "true" ]; then
        build_args="--cache-from $image_name"
    fi
    
    # Add build arguments
    build_args="$build_args --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    build_args="$build_args --build-arg VCS_REF=$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
    build_args="$build_args --build-arg VERSION=$TAG"
    
    # Build the image
    if docker buildx version >/dev/null 2>&1; then
        # Use BuildKit
        docker buildx build \
            --platform linux/amd64,linux/arm64 \
            --tag "$image_name" \
            --file "$service_path/$dockerfile" \
            $build_args \
            "$service_path"
    else
        # Use legacy builder
        docker build \
            --tag "$image_name" \
            --file "$service_path/$dockerfile" \
            $build_args \
            "$service_path"
    fi
    
    if [ $? -eq 0 ]; then
        log_success "Built $service_name successfully"
        
        # Push image if requested
        if [ "$PUSH_IMAGES" = "true" ]; then
            log_info "Pushing $image_name..."
            docker push "$image_name"
            log_success "Pushed $image_name"
        fi
        
        return 0
    else
        log_error "Failed to build $service_name"
        return 1
    fi
}

# Function to build services in parallel
build_services_parallel() {
    local services=("$@")
    local pids=()
    
    log_info "Building services in parallel..."
    
    for service_config in "${services[@]}"; do
        IFS=':' read -r name path dockerfile <<< "$service_config"
        dockerfile="${dockerfile:-Dockerfile}"
        
        (
            build_service "$name" "$path" "$dockerfile"
        ) &
        pids+=($!)
    done
    
    # Wait for all builds to complete
    local failed=0
    for pid in "${pids[@]}"; do
        if ! wait $pid; then
            failed=$((failed + 1))
        fi
    done
    
    if [ $failed -eq 0 ]; then
        log_success "All services built successfully"
        return 0
    else
        log_error "$failed service(s) failed to build"
        return 1
    fi
}

# Function to build services sequentially
build_services_sequential() {
    local services=("$@")
    local failed=0
    
    log_info "Building services sequentially..."
    
    for service_config in "${services[@]}"; do
        IFS=':' read -r name path dockerfile <<< "$service_config"
        dockerfile="${dockerfile:-Dockerfile}"
        
        if ! build_service "$name" "$path" "$dockerfile"; then
            failed=$((failed + 1))
        fi
    done
    
    if [ $failed -eq 0 ]; then
        log_success "All services built successfully"
        return 0
    else
        log_error "$failed service(s) failed to build"
        return 1
    fi
}

# Function to prune Docker resources
cleanup_docker() {
    log_info "Cleaning up Docker resources..."
    
    # Remove dangling images
    docker image prune -f
    
    # Remove unused build cache (keep some for next builds)
    if docker buildx version >/dev/null 2>&1; then
        docker buildx prune -f --keep-storage 1GB
    fi
    
    log_success "Docker cleanup completed"
}

# Function to display build summary
display_summary() {
    local start_time="$1"
    local end_time="$2"
    local duration=$((end_time - start_time))
    
    echo
    log_info "=== BUILD SUMMARY ==="
    echo "Registry: $REGISTRY"
    echo "Tag: $TAG"
    echo "Build time: ${duration}s"
    echo "Parallel build: $BUILD_PARALLEL"
    echo "Push images: $PUSH_IMAGES"
    echo
    
    # Show built images
    log_info "Built images:"
    docker images --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}" \
        --filter "reference=$REGISTRY/*:$TAG"
}

# Main build function
main() {
    log_info "Starting SaaSOdoo build process..."
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --registry)
                REGISTRY="$2"
                shift 2
                ;;
            --tag)
                TAG="$2"
                shift 2
                ;;
            --parallel)
                BUILD_PARALLEL="true"
                shift
                ;;
            --sequential)
                BUILD_PARALLEL="false"
                shift
                ;;
            --push)
                PUSH_IMAGES="true"
                shift
                ;;
            --no-cache)
                CACHE_FROM="false"
                shift
                ;;
            --cleanup)
                cleanup_docker
                exit 0
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo
                echo "Options:"
                echo "  --registry REGISTRY    Docker registry (default: saasodoo)"
                echo "  --tag TAG             Build tag (default: latest)"
                echo "  --parallel            Build services in parallel (default)"
                echo "  --sequential          Build services sequentially"
                echo "  --push                Push images to registry"
                echo "  --no-cache            Disable build cache"
                echo "  --cleanup             Clean up Docker resources and exit"
                echo "  --help                Show this help message"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    # Change to project root directory
    cd "$(dirname "$0")/../.."
    
    # Pre-build checks
    check_docker
    check_buildkit
    
    local start_time=$(date +%s)
    
    # Define services to build (name:path:dockerfile)
    local services=(
        "api-gateway:services/api-gateway"
        "auth-service:services/auth-service"
        "tenant-service:services/tenant-service"
        "billing-service:services/billing-service"
        "communication-service:services/communication-service"
        "analytics-service:services/analytics-service"
        "web-app:apps/web-app"
        "admin-app:apps/admin-app"
    )
    
    # Build services
    if [ "$BUILD_PARALLEL" = "true" ]; then
        build_services_parallel "${services[@]}"
    else
        build_services_sequential "${services[@]}"
    fi
    
    local build_result=$?
    local end_time=$(date +%s)
    
    # Display summary
    display_summary "$start_time" "$end_time"
    
    if [ $build_result -eq 0 ]; then
        log_success "Build process completed successfully!"
    else
        log_error "Build process completed with errors!"
        exit 1
    fi
}

# Handle script interruption
trap 'log_warning "Build interrupted by user"; exit 130' INT TERM

# Run main function
main "$@" 