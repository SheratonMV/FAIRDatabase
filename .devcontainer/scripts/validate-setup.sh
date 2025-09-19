#!/bin/bash
set -e

echo "==============================================="
echo " FAIRDatabase DevContainer Validation Script"
echo "==============================================="
echo ""

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track overall status
STATUS=0

# Function to check command availability
check_command() {
    local cmd=$1
    local name=$2
    if command -v $cmd &> /dev/null; then
        echo -e "${GREEN}✓${NC} $name is installed: $(command -v $cmd)"
        return 0
    else
        echo -e "${RED}✗${NC} $name is not installed"
        STATUS=1
        return 1
    fi
}

# Function to check file existence
check_file() {
    local file=$1
    local desc=$2
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $desc exists: $file"
        return 0
    else
        echo -e "${YELLOW}⚠${NC} $desc not found: $file"
        return 1
    fi
}

echo "1. Checking Docker Setup"
echo "------------------------"
check_command docker "Docker"
if [ $? -eq 0 ]; then
    docker --version
fi

if docker compose version &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker Compose is installed (plugin)"
    docker compose version
elif command -v "docker-compose" &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker Compose is installed (standalone)"
    docker-compose --version
else
    echo -e "${RED}✗${NC} Docker Compose is not installed"
    STATUS=1
fi
echo ""

echo "2. Checking DevContainer CLI"
echo "----------------------------"
check_command devcontainer "DevContainer CLI"
if [ $? -eq 0 ]; then
    devcontainer --version
fi
echo ""

echo "3. Checking DevContainer Configuration"
echo "--------------------------------------"
check_file ".devcontainer/devcontainer.json" "DevContainer config"
check_file ".devcontainer/scripts/postCreate.sh" "PostCreate script"
check_file ".devcontainer/scripts/postStart.sh" "PostStart script"

# Check if scripts are executable
if [ -f ".devcontainer/scripts/postCreate.sh" ]; then
    if [ -x ".devcontainer/scripts/postCreate.sh" ]; then
        echo -e "${GREEN}✓${NC} postCreate.sh is executable"
    else
        echo -e "${RED}✗${NC} postCreate.sh is not executable"
        STATUS=1
    fi
fi

if [ -f ".devcontainer/scripts/postStart.sh" ]; then
    if [ -x ".devcontainer/scripts/postStart.sh" ]; then
        echo -e "${GREEN}✓${NC} postStart.sh is executable"
    else
        echo -e "${RED}✗${NC} postStart.sh is not executable"
        STATUS=1
    fi
fi
echo ""

echo "4. Checking Project Structure"
echo "-----------------------------"
check_file "backend/requirements.txt" "Python requirements"
check_file "backend/requirements-dev.txt" "Python dev requirements"
check_file "package.json" "Node package.json"
echo ""

echo "5. Testing Container Image Access"
echo "---------------------------------"
echo "Pulling base image..."
if docker pull mcr.microsoft.com/devcontainers/python:3.13 &> /dev/null; then
    echo -e "${GREEN}✓${NC} Base image accessible: mcr.microsoft.com/devcontainers/python:3.13"
else
    echo -e "${RED}✗${NC} Failed to pull base image"
    STATUS=1
fi
echo ""

echo "6. Quick Container Test"
echo "----------------------"
echo "Running Python version check in container..."
if docker run --rm mcr.microsoft.com/devcontainers/python:3.13 python --version &> /dev/null; then
    VERSION=$(docker run --rm mcr.microsoft.com/devcontainers/python:3.13 python --version 2>&1)
    echo -e "${GREEN}✓${NC} Container Python: $VERSION"
else
    echo -e "${RED}✗${NC} Failed to run Python in container"
    STATUS=1
fi
echo ""

echo "7. DevContainer JSON Validation"
echo "-------------------------------"
if [ -f ".devcontainer/devcontainer.json" ]; then
    # Basic JSON syntax check using Python
    if python3 -c "import json; json.load(open('.devcontainer/devcontainer.json'))" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} devcontainer.json is valid JSON"

        # Extract and display key configuration
        echo ""
        echo "Configuration Summary:"
        python3 -c "
import json
with open('.devcontainer/devcontainer.json') as f:
    config = json.load(f)
    print(f'  - Container Name: {config.get(\"name\", \"Not specified\")}')
    print(f'  - Base Image: {config.get(\"image\", \"Not specified\")}')
    print(f'  - Features Count: {len(config.get(\"features\", {}))}')
    if 'features' in config:
        for feature in config['features']:
            print(f'    • {feature}')
    print(f'  - Forward Ports: {config.get(\"forwardPorts\", [])}')
"
    else
        echo -e "${RED}✗${NC} devcontainer.json has invalid JSON syntax"
        STATUS=1
    fi
fi
echo ""

echo "==============================================="
if [ $STATUS -eq 0 ]; then
    echo -e "${GREEN}✅ All checks passed!${NC}"
    echo ""
    echo "You can now use the devcontainer with:"
    echo "  - VS Code: Open in Container"
    echo "  - CLI: devcontainer up --workspace-folder ."
else
    echo -e "${RED}❌ Some checks failed. Please review the issues above.${NC}"
fi
echo "==============================================="

exit $STATUS