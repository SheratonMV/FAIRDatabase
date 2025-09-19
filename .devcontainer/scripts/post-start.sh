#!/bin/bash

# =============================================================================
# post-start.sh - Container startup tasks
# Runs each time the container starts
# Responsibility: Start services and display development information
# =============================================================================

# Source shared utilities
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "${SCRIPT_DIR}/utils.sh"

# -----------------------------------------------------------------------------
# MAIN STARTUP PROCESS
# -----------------------------------------------------------------------------

main() {
    log_section "🎯 FAIRDatabase DevContainer - Startup"

    # Start essential services
    start_supabase_services

    # Setup development environment
    setup_mcp_servers
    verify_python_environment

    # Display helpful information
    display_service_urls
    display_quick_commands

    log_section "✅ Container Ready"
    log_success "Happy coding! 🎉"
}

# -----------------------------------------------------------------------------
# SUPABASE SERVICE MANAGEMENT
# -----------------------------------------------------------------------------

start_supabase_services() {
    log_info "Managing Supabase services..."

    cd "$PROJECT_ROOT" || exit 1

    # Initialize Supabase if needed
    if [[ ! -f "supabase/config.toml" ]]; then
        log_warn "Supabase not initialized - initializing now..."
        npx supabase init || {
            log_error "Failed to initialize Supabase"
            log_info "Initialize manually with: npx supabase init"
            return 1
        }
        log_success "Supabase initialized"
    fi

    # Check if Supabase is already running
    if service_running "Supabase" "npx supabase status 2>/dev/null | grep -q RUNNING"; then
        log_success "Supabase services are already running"
    else
        log_info "Starting Supabase services (this may take a moment)..."

        # Start Supabase with timeout handling
        if timeout 60 npx supabase start 2>&1 | tee /tmp/supabase-start.log; then
            log_success "Supabase services started successfully"
        else
            log_warn "Supabase services failed to start"
            log_info "Check logs at /tmp/supabase-start.log"
            log_info "Start manually with: npx supabase start"
            # Non-fatal - continue startup
        fi
    fi
}

# -----------------------------------------------------------------------------
# MCP SERVER SETUP
# -----------------------------------------------------------------------------

setup_mcp_servers() {
    log_info "Configuring MCP servers for AI assistance..."

    local mcp_script="${SCRIPTS_DIR}/mcp-setup.sh"

    if [[ -x "$mcp_script" ]]; then
        # Run MCP setup in background to avoid blocking startup
        (
            bash "$mcp_script" &> /tmp/mcp-setup.log || {
                log_warn "MCP setup encountered issues"
                log_info "Check logs at /tmp/mcp-setup.log"
                log_info "Run manually with: ${mcp_script}"
            }
        ) &

        log_info "MCP setup running in background - check 'claude mcp list' shortly"
    else
        log_debug "MCP setup script not found or not executable: $mcp_script"
    fi
}

# -----------------------------------------------------------------------------
# PYTHON ENVIRONMENT VERIFICATION
# -----------------------------------------------------------------------------

verify_python_environment() {
    log_info "Verifying Python environment..."

    # Display Python version
    if command_exists "python"; then
        local python_version=$(python --version 2>&1)
        log_success "Python: $python_version"
    else
        log_error "Python is not available"
        exit 1
    fi

    # Check virtual environment
    if is_venv_active; then
        log_success "Virtual environment active: $VIRTUAL_ENV"
    else
        log_warn "Virtual environment not active"
        log_info "Activate with: source ${VENV_PATH}/bin/activate"
    fi
}

# -----------------------------------------------------------------------------
# INFORMATION DISPLAY
# -----------------------------------------------------------------------------

display_service_urls() {
    log_section "🌐 Service URLs"

    echo "  Flask Backend:    http://localhost:5000"
    echo "  Supabase Studio:  http://localhost:54321"
    echo "  Supabase API:     http://localhost:54323"
    echo ""
}

display_quick_commands() {
    log_section "📚 Quick Reference"

    echo "Development Commands:"
    echo "  cd backend && uv run python app.py  # Start backend"
    echo "  cd backend && uv run pytest         # Run tests"
    echo "  uv run ruff check .                 # Check code"
    echo "  uv run ruff format .                # Format code"
    echo ""

    echo "Package Management (use uv, not pip):"
    echo "  uv add <package>                    # Add dependency"
    echo "  uv add --group dev <package>        # Add dev dependency"
    echo "  uv sync                             # Sync dependencies"
    echo "  uv pip list                         # List packages"
    echo ""

    if command_exists "claude"; then
        echo "AI Assistant:"
        echo "  claude                              # Get AI help"
        echo "  claude mcp list                     # List MCP servers"
        echo "  claude doctor                       # Check health"
        echo ""
    fi
}

# -----------------------------------------------------------------------------
# EXECUTE MAIN FUNCTION
# -----------------------------------------------------------------------------

main "$@"