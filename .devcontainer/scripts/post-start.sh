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

    # Check for Git configuration reminder
    if [[ -f "$HOME/.git-config-reminder" ]]; then
        echo ""
        cat "$HOME/.git-config-reminder"
        echo ""
    fi

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
    if npx supabase status &>/dev/null; then
        log_success "Supabase services are already running"
        return 0
    fi

    log_info "Starting Supabase services..."
    log_info "First startup requires downloading Docker images (~1.5GB) - this may take several minutes..."

    # Start Supabase in background and capture the output
    # No timeout - let it take as long as needed
    (
        npx supabase start > /tmp/supabase-start.log 2>&1
        echo $? > /tmp/supabase-start-exit-code
    ) &
    local supabase_pid=$!

    # Wait for startup with progress indicator (no timeout)
    local wait_time=0

    while true; do
        if ! kill -0 $supabase_pid 2>/dev/null; then
            # Process finished
            local exit_code=$(cat /tmp/supabase-start-exit-code 2>/dev/null || echo "1")
            if [ "$exit_code" -eq 0 ]; then
                log_success "Supabase services started successfully"
                return 0
            else
                log_warn "Supabase startup completed with issues"
                log_info "Check logs at /tmp/supabase-start.log"
                log_info "You can retry with: npx supabase start"
                return 1
            fi
        fi

        # Show progress
        if [ $((wait_time % 10)) -eq 0 ]; then
            echo -n "."
        fi

        sleep 1
        ((wait_time++))
    done
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
    echo "  Supabase Studio:  http://localhost:54323"
    echo "  Supabase API:     http://localhost:54321"
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