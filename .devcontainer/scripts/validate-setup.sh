#!/bin/bash

# =============================================================================
# validate-setup.sh - DevContainer Setup Validation
# Responsibility: Verify that the development environment is correctly configured
# =============================================================================

# Don't exit on error for validation script - we want to check everything
set +e

# Source shared utilities
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "${SCRIPT_DIR}/utils.sh"

# Override error handling for this script
set +e
trap - ERR

# -----------------------------------------------------------------------------
# VALIDATION STATE
# -----------------------------------------------------------------------------

# Track validation results
declare -i CHECKS_PASSED=0
declare -i CHECKS_FAILED=0
declare -i CHECKS_WARNING=0

# -----------------------------------------------------------------------------
# VALIDATION HELPERS
# -----------------------------------------------------------------------------

# Record a successful check
check_pass() {
    local message="$1"
    echo -e "${COLOR_GREEN}✓${COLOR_RESET} $message"
    ((CHECKS_PASSED++))
}

# Record a failed check
check_fail() {
    local message="$1"
    echo -e "${COLOR_RED}✗${COLOR_RESET} $message"
    ((CHECKS_FAILED++))
}

# Record a warning
check_warn() {
    local message="$1"
    echo -e "${COLOR_YELLOW}⚠${COLOR_RESET} $message"
    ((CHECKS_WARNING++))
}

# Validate command exists and record result
validate_command() {
    local cmd="$1"
    local name="${2:-$cmd}"
    local required="${3:-true}"

    if command_exists "$cmd"; then
        local location=$(command -v "$cmd")
        check_pass "$name is installed: $location"
        return 0
    else
        if [[ "$required" == "true" ]]; then
            check_fail "$name is not installed"
        else
            check_warn "$name is not installed (optional)"
        fi
        return 1
    fi
}

# Validate file exists and record result
validate_file() {
    local file="$1"
    local desc="$2"
    local required="${3:-true}"

    if [[ -f "$file" ]]; then
        check_pass "$desc exists"
        return 0
    else
        if [[ "$required" == "true" ]]; then
            check_fail "$desc not found: $file"
        else
            check_warn "$desc not found: $file (optional)"
        fi
        return 1
    fi
}

# Validate directory exists and record result
validate_directory() {
    local dir="$1"
    local desc="$2"
    local required="${3:-true}"

    if [[ -d "$dir" ]]; then
        check_pass "$desc exists"
        return 0
    else
        if [[ "$required" == "true" ]]; then
            check_fail "$desc not found: $dir"
        else
            check_warn "$desc not found: $dir (optional)"
        fi
        return 1
    fi
}

# -----------------------------------------------------------------------------
# VALIDATION SECTIONS
# -----------------------------------------------------------------------------

validate_docker_setup() {
    log_info "Checking Docker Setup..."

    # Check Docker
    if validate_command "docker" "Docker"; then
        local version=$(docker --version 2>&1)
        log_debug "Docker version: $version"
    fi

    # Check Docker Compose
    if docker compose version &> /dev/null; then
        check_pass "Docker Compose is installed (plugin)"
        log_debug "$(docker compose version 2>&1)"
    elif command_exists "docker-compose"; then
        check_pass "Docker Compose is installed (standalone)"
        log_debug "$(docker-compose --version 2>&1)"
    else
        check_fail "Docker Compose is not installed"
    fi

    echo ""
}

validate_devcontainer_cli() {
    log_info "Checking DevContainer CLI..."

    if validate_command "devcontainer" "DevContainer CLI" "false"; then
        local version=$(devcontainer --version 2>&1)
        log_debug "DevContainer version: $version"
    fi

    echo ""
}

validate_devcontainer_config() {
    log_info "Checking DevContainer Configuration..."

    # Check configuration files
    validate_file ".devcontainer/devcontainer.json" "DevContainer config"
    validate_file ".devcontainer/scripts/post-create.sh" "PostCreate script"
    validate_file ".devcontainer/scripts/post-start.sh" "PostStart script"
    validate_file ".devcontainer/scripts/mcp-setup.sh" "MCP setup script" "false"
    validate_file ".devcontainer/scripts/utils.sh" "Utility functions"

    # Check script permissions
    for script in post-create.sh post-start.sh mcp-setup.sh utils.sh validate-setup.sh; do
        local script_path=".devcontainer/scripts/$script"
        if [[ -f "$script_path" ]]; then
            if [[ -x "$script_path" ]]; then
                check_pass "$script is executable"
            else
                check_warn "$script is not executable (run: chmod +x $script_path)"
            fi
        fi
    done

    echo ""
}

validate_project_structure() {
    log_info "Checking Project Structure..."

    # Check directories
    validate_directory "backend" "Backend directory"
    validate_directory "frontend" "Frontend directory" "false"
    validate_directory ".devcontainer" "DevContainer directory"

    # Check Python configuration
    validate_file "backend/pyproject.toml" "Python project config"
    validate_file "backend/uv.lock" "Python lock file" "false"

    # Legacy files (warn if present)
    if [[ -f "backend/requirements.txt" ]]; then
        check_warn "Legacy requirements.txt found - project uses pyproject.toml now"
    fi

    # Check Node configuration
    validate_file "package.json" "Node package.json" "false"
    validate_file "package-lock.json" "Node lock file" "false"

    # Check environment files
    validate_file "backend/.env.sample" "Environment template" "false"

    echo ""
}

validate_container_image() {
    log_info "Testing Container Image Access..."

    local base_image="mcr.microsoft.com/devcontainers/python:3.13"

    log_debug "Checking base image: $base_image"

    if docker pull "$base_image" &> /dev/null; then
        check_pass "Base image accessible: $base_image"
    else
        check_fail "Failed to pull base image: $base_image"
        log_info "Check your internet connection and Docker configuration"
    fi

    echo ""
}

validate_container_runtime() {
    log_info "Testing Container Runtime..."

    local base_image="mcr.microsoft.com/devcontainers/python:3.13"

    if output=$(docker run --rm "$base_image" python --version 2>&1); then
        check_pass "Container Python: $output"
    else
        check_fail "Failed to run Python in container"
        log_debug "Error output: $output"
    fi

    echo ""
}

validate_devcontainer_json() {
    log_info "Validating DevContainer JSON..."

    local config_file=".devcontainer/devcontainer.json"

    if [[ ! -f "$config_file" ]]; then
        check_fail "DevContainer config not found"
        return 1
    fi

    # Validate JSON syntax
    if python3 -c "import json; json.load(open('$config_file'))" 2>/dev/null; then
        check_pass "devcontainer.json has valid JSON syntax"

        # Extract and display configuration
        log_info "Configuration Summary:"
        python3 -c "
import json
import sys
try:
    with open('$config_file') as f:
        config = json.load(f)
        print(f'  Container Name: {config.get(\"name\", \"Not specified\")}')
        print(f'  Base Image: {config.get(\"image\", \"Not specified\")}')

        features = config.get(\"features\", {})
        if features:
            print(f'  Features ({len(features)}): ')
            for feature in features:
                print(f'    • {feature}')

        ports = config.get(\"forwardPorts\", [])
        if ports:
            print(f'  Forward Ports: {\", \".join(map(str, ports))}')

        extensions = config.get(\"customizations\", {}).get(\"vscode\", {}).get(\"extensions\", [])
        if extensions:
            print(f'  VS Code Extensions: {len(extensions)} configured')
except Exception as e:
    print(f'Error parsing config: {e}', file=sys.stderr)
    sys.exit(1)
" || check_warn "Failed to parse configuration details"
    else
        check_fail "devcontainer.json has invalid JSON syntax"
        log_info "Validate JSON at: https://jsonlint.com/"
    fi

    echo ""
}

validate_development_tools() {
    log_info "Checking Development Tools..."

    # Python tools
    validate_command "python" "Python" "false"
    validate_command "python3" "Python 3"
    validate_command "uv" "uv (Python package manager)" "false"
    validate_command "pip" "pip" "false"

    # Node.js tools
    validate_command "node" "Node.js" "false"
    validate_command "npm" "npm" "false"

    # Development tools
    validate_command "git" "Git"
    validate_command "ruff" "Ruff (Python linter)" "false"
    validate_command "pytest" "pytest" "false"

    # AI tools
    validate_command "claude" "Claude Code CLI" "false"

    echo ""
}

# -----------------------------------------------------------------------------
# MAIN VALIDATION PROCESS
# -----------------------------------------------------------------------------

main() {
    log_section "🔍 FAIRDatabase DevContainer Validation"

    # Run all validation checks
    validate_docker_setup
    validate_devcontainer_cli
    validate_devcontainer_config
    validate_project_structure
    validate_container_image
    validate_container_runtime
    validate_devcontainer_json
    validate_development_tools

    # Display summary
    display_validation_summary

    # Return appropriate exit code
    if [[ $CHECKS_FAILED -gt 0 ]]; then
        exit 1
    else
        exit 0
    fi
}

# -----------------------------------------------------------------------------
# SUMMARY DISPLAY
# -----------------------------------------------------------------------------

display_validation_summary() {
    log_section "Validation Summary"

    echo "Checks Passed:  ${COLOR_GREEN}$CHECKS_PASSED${COLOR_RESET}"
    echo "Checks Failed:  ${COLOR_RED}$CHECKS_FAILED${COLOR_RESET}"
    echo "Warnings:       ${COLOR_YELLOW}$CHECKS_WARNING${COLOR_RESET}"
    echo ""

    if [[ $CHECKS_FAILED -eq 0 ]]; then
        log_success "All critical checks passed! 🎆"
        echo ""
        log_info "You can now use the devcontainer with:"
        echo "  VS Code:  Reopen in Container (Cmd/Ctrl+Shift+P)"
        echo "  CLI:      devcontainer up --workspace-folder ."
    else
        log_error "Some critical checks failed. Please review the issues above."
        echo ""
        log_info "Common fixes:"
        echo "  - Ensure Docker is running"
        echo "  - Check file permissions: chmod +x .devcontainer/scripts/*.sh"
        echo "  - Pull the base image manually: docker pull mcr.microsoft.com/devcontainers/python:3.13"
    fi

    if [[ $CHECKS_WARNING -gt 0 ]]; then
        echo ""
        log_warn "Some optional features are not configured."
        log_info "These won't prevent the container from working but may limit functionality."
    fi
}

# -----------------------------------------------------------------------------
# EXECUTE MAIN FUNCTION
# -----------------------------------------------------------------------------

main "$@"