#!/bin/bash
#
# SaaSOdoo Load Test Runner
#
# Usage:
#   ./run_tests.sh registration    # Test user registration only
#   ./run_tests.sh auth            # Test authentication flow only
#   ./run_tests.sh health          # Test health endpoints (baseline)
#   ./run_tests.sh mixed           # Mixed workload
#   ./run_tests.sh all             # All tests (default)
#   ./run_tests.sh web             # Start web UI

set -e

# Configuration
HOST="${LOAD_TEST_HOST:-http://api.62.171.153.219.nip.io}"
USERS="${LOAD_TEST_USERS:-50}"
SPAWN_RATE="${LOAD_TEST_SPAWN_RATE:-5}"
RUN_TIME="${LOAD_TEST_RUN_TIME:-2m}"
LOCUST_FILE="locustfile.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}======================================${NC}"
echo -e "${YELLOW}SaaSOdoo Capacity Load Tests${NC}"
echo -e "${YELLOW}======================================${NC}"
echo ""
echo -e "Target Host: ${GREEN}$HOST${NC}"
echo -e "Users: ${GREEN}$USERS${NC}"
echo -e "Spawn Rate: ${GREEN}$SPAWN_RATE/sec${NC}"
echo -e "Run Time: ${GREEN}$RUN_TIME${NC}"
echo ""

# Check if locust is installed
if ! command -v locust &> /dev/null; then
    echo -e "${RED}Locust is not installed!${NC}"
    echo "Install with: pip install -r requirements.txt"
    exit 1
fi

# Parse test type
TEST_TYPE="${1:-all}"

case $TEST_TYPE in
    registration)
        echo -e "${YELLOW}Running: User Registration Tests${NC}"
        echo -e "${RED}WARNING: This creates REAL users and KillBill accounts!${NC}"
        echo ""
        read -p "Continue? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 0
        fi
        locust -f $LOCUST_FILE \
            --host=$HOST \
            --headless \
            -u $USERS \
            -r $SPAWN_RATE \
            -t $RUN_TIME \
            --tags registration \
            --only-summary \
            --csv=results/registration_$(date +%Y%m%d_%H%M%S)
        ;;

    auth)
        echo -e "${YELLOW}Running: Authentication Flow Tests${NC}"
        echo -e "${RED}Note: Creates one user per virtual user for auth testing${NC}"
        echo ""
        locust -f $LOCUST_FILE \
            --host=$HOST \
            --headless \
            -u $USERS \
            -r $SPAWN_RATE \
            -t $RUN_TIME \
            --tags auth \
            --only-summary \
            --csv=results/auth_$(date +%Y%m%d_%H%M%S)
        ;;

    health)
        echo -e "${YELLOW}Running: Health Check Tests (Baseline)${NC}"
        echo ""
        locust -f $LOCUST_FILE \
            --host=$HOST \
            --headless \
            -u $USERS \
            -r $SPAWN_RATE \
            -t $RUN_TIME \
            --tags health \
            --only-summary \
            --csv=results/health_$(date +%Y%m%d_%H%M%S)
        ;;

    mixed)
        echo -e "${YELLOW}Running: Mixed Workload Tests${NC}"
        echo -e "${RED}WARNING: This creates REAL users and KillBill accounts!${NC}"
        echo ""
        read -p "Continue? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 0
        fi
        locust -f $LOCUST_FILE \
            --host=$HOST \
            --headless \
            -u $USERS \
            -r $SPAWN_RATE \
            -t $RUN_TIME \
            --tags mixed \
            --only-summary \
            --csv=results/mixed_$(date +%Y%m%d_%H%M%S)
        ;;

    web)
        echo -e "${YELLOW}Starting Locust Web UI${NC}"
        echo -e "Open ${GREEN}http://localhost:8089${NC} in your browser"
        echo ""
        locust -f $LOCUST_FILE --host=$HOST
        ;;

    all)
        echo -e "${YELLOW}Running: All Tests${NC}"
        echo -e "${RED}WARNING: This creates REAL users and KillBill accounts!${NC}"
        echo ""
        read -p "Continue? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 0
        fi
        locust -f $LOCUST_FILE \
            --host=$HOST \
            --headless \
            -u $USERS \
            -r $SPAWN_RATE \
            -t $RUN_TIME \
            --only-summary \
            --csv=results/all_$(date +%Y%m%d_%H%M%S)
        ;;

    *)
        echo "Usage: $0 {registration|auth|health|mixed|web|all}"
        echo ""
        echo "Test Types:"
        echo "  registration  - Test user registration throughput (creates real users)"
        echo "  auth          - Test login/logout/session validation"
        echo "  health        - Baseline health endpoint testing"
        echo "  mixed         - Mixed realistic workload"
        echo "  web           - Start Locust web UI at http://localhost:8089"
        echo "  all           - Run all tests"
        echo ""
        echo "Environment Variables:"
        echo "  LOAD_TEST_HOST       - Target host (default: http://api.62.171.153.219.nip.io)"
        echo "  LOAD_TEST_USERS      - Number of concurrent users (default: 50)"
        echo "  LOAD_TEST_SPAWN_RATE - Users to spawn per second (default: 5)"
        echo "  LOAD_TEST_RUN_TIME   - Test duration (default: 2m)"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}Test Complete!${NC}"
echo "Results saved to ./results/"
