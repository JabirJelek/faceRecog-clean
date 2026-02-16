#!/bin/bash
# Test runner script for VoyagerFaceRecognitionSystem

set -e

echo "Voyager System Test Suite"
echo "=========================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ $2${NC}"
    else
        echo -e "${RED}✗ $2${NC}"
    fi
}

# Create test directory
TEST_DIR=$(mktemp -d /tmp/voyager_test_XXXXXX)
echo "Test directory: $TEST_DIR"

# Install requirements if needed
echo -e "\n${YELLOW}Checking dependencies...${NC}"
pip install -q numpy torch pytest psutil

# Run tests
echo -e "\n${YELLOW}Running quick smoke test...${NC}"
python -m tests.test_voyager_system --quick
SMOKE_TEST_RESULT=$?
print_status $SMOKE_TEST_RESULT "Smoke test"

if [ $SMOKE_TEST_RESULT -eq 0 ]; then
    echo -e "\n${YELLOW}Running unit tests...${NC}"
    python -m pytest tests/test_voyager_system.py::TestVoyagerFaceRecognitionSystem -v
    UNIT_TEST_RESULT=$?
    print_status $UNIT_TEST_RESULT "Unit tests"
    
    echo -e "\n${YELLOW}Running performance benchmarks...${NC}"
    python -m tests.test_voyager_system --benchmark
    BENCHMARK_RESULT=$?
    print_status $BENCHMARK_RESULT "Benchmarks"
    
    # Generate test report
    echo -e "\n${YELLOW}Generating test report...${NC}"
    REPORT_FILE="$TEST_DIR/test_report_$(date +%Y%m%d_%H%M%S).txt"
    python -m tests.test_voyager_system 2>&1 | tee "$REPORT_FILE"
    
    echo -e "\n${YELLOW}Test report saved to: $REPORT_FILE${NC}"
    
    # Check overall result
    if [ $UNIT_TEST_RESULT -eq 0 ] && [ $BENCHMARK_RESULT -eq 0 ]; then
        echo -e "\n${GREEN}All tests passed!${NC}"
        exit 0
    else
        echo -e "\n${RED}Some tests failed${NC}"
        exit 1
    fi
else
    echo -e "\n${RED}Smoke test failed, skipping further tests${NC}"
    exit 1
fi