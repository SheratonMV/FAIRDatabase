#!/bin/bash

# =============================================================================
# Shared utility functions for FAIRDatabase devcontainer scripts
# Provides consistent error handling, logging, and common operations
# =============================================================================

# Exit on any error, undefined variable, or pipe failure
set -euo pipefail

# -----------------------------------------------------------------------------
# CONSTANTS
# -----------------------------------------------------------------------------
readonly PROJECT_ROOT="/workspaces/FAIRDatabase"
readonly BACKEND_DIR="${PROJECT_ROOT}/backend"
readonly VENV_PATH="${BACKEND_DIR}/.venv"
readonly SCRIPTS_DIR="${PROJECT_ROOT}/.devcontainer/scripts"

# Color codes for consistent output formatting
readonly COLOR_RED='\033[0;31m'
readonly COLOR_GREEN='\033[0;32m'
readonly COLOR_YELLOW='\033[1;33m'
readonly COLOR_BLUE='\033[0;34m'
readonly COLOR_RESET='\033[0m'

# Log levels
readonly LOG_ERROR=0
readonly LOG_WARN=1
readonly LOG_INFO=2
readonly LOG_SUCCESS=3
readonly LOG_DEBUG=4

# -----------------------------------------------------------------------------
# LOGGING FUNCTIONS
# -----------------------------------------------------------------------------

# Log message with appropriate color and prefix
log() {
    local level="$1"
    shift
    local message="$*"

    case "$level" in
        $LOG_ERROR)
            echo -e "${COLOR_RED}❌ ERROR:${COLOR_RESET} $message" >&2
            ;;
        $LOG_WARN)
            echo -e "${COLOR_YELLOW}⚠️  WARNING:${COLOR_RESET} $message"
            ;;
        $LOG_INFO)
            echo -e "${COLOR_BLUE}ℹ️  INFO:${COLOR_RESET} $message"
            ;;
        $LOG_SUCCESS)
            echo -e "${COLOR_GREEN}✅ SUCCESS:${COLOR_RESET} $message"
            ;;
        $LOG_DEBUG)
            [[ "${DEBUG:-0}" == "1" ]] && echo -e "🐛 DEBUG: $message"
            ;;
    esac
}

log_error() { log $LOG_ERROR "$@"; }
log_warn() { log $LOG_WARN "$@"; }
log_info() { log $LOG_INFO "$@"; }
log_success() { log $LOG_SUCCESS "$@"; }
log_debug() { log $LOG_DEBUG "$@"; }

# Log section header for visual separation
log_section() {
    echo ""
    echo "════════════════════════════════════════════════"
    echo " $1"
    echo "════════════════════════════════════════════════"
    echo ""
}

# -----------------------------------------------------------------------------
# ERROR HANDLING
# -----------------------------------------------------------------------------

# Trap errors and provide context
error_handler() {
    local line_number="$1"
    local bash_lineno="$2"
    local last_command="$3"

    log_error "Command failed at line $line_number: $last_command"
    log_error "Call stack: ${BASH_SOURCE[1]}:${bash_lineno}"

    # Provide actionable error message
    echo ""
    echo "💡 To debug this error:"
    echo "   1. Check the command output above"
    echo "   2. Run with DEBUG=1 for more details"
    echo "   3. Check logs in /tmp/devcontainer-setup.log"

    exit 1
}

# Set up error trap
trap 'error_handler $LINENO $BASH_LINENO "$BASH_COMMAND"' ERR

# -----------------------------------------------------------------------------
# VALIDATION FUNCTIONS
# -----------------------------------------------------------------------------

# Check if a command exists
command_exists() {
    local cmd="$1"
    command -v "$cmd" &> /dev/null
}

# Require a command to be available or fail
require_command() {
    local cmd="$1"
    local package="${2:-$cmd}"

    if ! command_exists "$cmd"; then
        log_error "Required command '$cmd' is not installed"
        log_info "Install it with: apt-get install $package (or appropriate package manager)"
        return 1
    fi

    log_debug "Found command: $cmd at $(command -v "$cmd")"
    return 0
}

# Check if running in expected environment
validate_environment() {
    if [[ ! -d "$PROJECT_ROOT" ]]; then
        log_error "Not in expected project directory: $PROJECT_ROOT"
        return 1
    fi

    if [[ "${CODESPACES:-false}" == "true" ]]; then
        log_info "Running in GitHub Codespaces"
    elif [[ -f "/.dockerenv" ]]; then
        log_info "Running in Docker container"
    else
        log_warn "Not running in container environment - some features may not work"
    fi

    return 0
}

# -----------------------------------------------------------------------------
# FILE OPERATIONS
# -----------------------------------------------------------------------------

# Safely create directory
safe_mkdir() {
    local dir="$1"

    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir" || {
            log_error "Failed to create directory: $dir"
            return 1
        }
        log_debug "Created directory: $dir"
    fi
}

# Safely copy file with backup
safe_copy() {
    local source="$1"
    local dest="$2"

    if [[ ! -f "$source" ]]; then
        log_error "Source file does not exist: $source"
        return 1
    fi

    if [[ -f "$dest" ]]; then
        cp "$dest" "${dest}.backup.$(date +%Y%m%d_%H%M%S)"
        log_debug "Backed up existing file: $dest"
    fi

    cp "$source" "$dest" || {
        log_error "Failed to copy $source to $dest"
        return 1
    }

    log_debug "Copied: $source -> $dest"
}

# -----------------------------------------------------------------------------
# PYTHON ENVIRONMENT
# -----------------------------------------------------------------------------

# Check if Python virtual environment is active
is_venv_active() {
    [[ -n "${VIRTUAL_ENV:-}" ]] && [[ "$VIRTUAL_ENV" == "$VENV_PATH" ]]
}

# Activate Python virtual environment
activate_venv() {
    if is_venv_active; then
        log_debug "Virtual environment already active: $VIRTUAL_ENV"
        return 0
    fi

    if [[ -f "${VENV_PATH}/bin/activate" ]]; then
        source "${VENV_PATH}/bin/activate"
        log_success "Activated virtual environment: $VENV_PATH"
        return 0
    else
        log_error "Virtual environment not found at: $VENV_PATH"
        return 1
    fi
}

# Run command in virtual environment
run_in_venv() {
    local cmd="$@"

    if is_venv_active; then
        eval "$cmd"
    elif [[ -f "${VENV_PATH}/bin/activate" ]]; then
        (
            source "${VENV_PATH}/bin/activate"
            eval "$cmd"
        )
    else
        log_warn "Running without virtual environment: $cmd"
        eval "$cmd"
    fi
}

# -----------------------------------------------------------------------------
# SERVICE MANAGEMENT
# -----------------------------------------------------------------------------

# Check if a service is running
service_running() {
    local service="$1"
    local check_command="$2"

    if eval "$check_command" &> /dev/null; then
        log_debug "Service '$service' is running"
        return 0
    else
        log_debug "Service '$service' is not running"
        return 1
    fi
}

# Wait for service to be ready (no timeout)
wait_for_service() {
    local service="$1"
    local check_command="$2"

    log_info "Waiting for $service to be ready..."

    while ! eval "$check_command" &> /dev/null; do
        sleep 1
        echo -n "."
    done

    echo ""
    log_success "$service is ready"
    return 0
}

# -----------------------------------------------------------------------------
# CLAUDE CODE SPECIFIC
# -----------------------------------------------------------------------------

# Install Claude Code CLI via npm
install_claude_code() {
    if command_exists "claude"; then
        log_success "Claude Code is already installed: $(claude --version 2>&1 | head -1)"
        return 0
    fi

    log_info "Installing Claude Code CLI..."

    # Require npm for installation
    if ! command_exists "npm"; then
        log_error "npm is not available and required for Claude Code installation"
        log_info "Please install npm first"
        return 1
    fi

    # Install via npm
    if npm install -g @anthropic-ai/claude-code 2>/dev/null; then
        log_success "Claude Code installed via npm"
    else
        log_error "Failed to install Claude Code CLI via npm"
        log_info "Try manually: npm install -g @anthropic-ai/claude-code"
        return 1
    fi

    # Verify installation
    if command_exists "claude"; then
        log_success "Claude Code ready: $(claude --version 2>&1 | head -1)"
        return 0
    else
        log_error "Claude Code installation verification failed"
        return 1
    fi
}

# Check Claude Code availability
check_claude_code() {
    if command_exists "claude"; then
        log_debug "Claude Code is available"
        return 0
    else
        log_warn "Claude Code is not installed"
        log_info "Install with: npm install -g @anthropic-ai/claude-code"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# EXPORT FUNCTIONS FOR USE IN OTHER SCRIPTS
# -----------------------------------------------------------------------------
export -f log log_error log_warn log_info log_success log_debug log_section
export -f command_exists require_command validate_environment
export -f safe_mkdir safe_copy
export -f is_venv_active activate_venv run_in_venv
export -f service_running wait_for_service
export -f install_claude_code check_claude_code