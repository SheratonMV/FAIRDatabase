#!/bin/bash

# =============================================================================
# post-start.sh - Container startup tasks
# Runs each time the container starts
# Responsibility: Start services and display development information
# =============================================================================

# Source shared utilities
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "${SCRIPT_DIR}/utils.sh"

# Use strict error handling to ensure critical services start properly
# This ensures the container won't be marked as ready until Supabase is fully operational

# -----------------------------------------------------------------------------
# MAIN STARTUP PROCESS
# -----------------------------------------------------------------------------

main() {
    log_section "🎯 FAIRDatabase DevContainer - Startup"

    # Check Claude availability once at startup
    CLAUDE_AVAILABLE=false
    if command_exists "claude"; then
        CLAUDE_AVAILABLE=true
    fi

    # Check for Git configuration reminder
    if [[ -f "$HOME/.git-config-reminder" ]]; then
        echo ""
        cat "$HOME/.git-config-reminder"
        echo ""
    fi

    # Start essential services (wait for Supabase to complete)
    log_info "Starting Supabase services - this is required for development"
    start_supabase_services || {
        log_error "Supabase failed to start - container startup incomplete"
        log_info "Check logs at /tmp/supabase-start.log for details"
        log_info "You can retry with: npx supabase start"
        exit 1
    }

    # Setup development environment (critical services)
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
    log_info "First startup requires downloading Docker images (~1.5GB)"
    log_info "This will block container startup until complete - please wait..."

    # Start Supabase with full output streaming for transparency
    if npx supabase start 2>&1 | tee /tmp/supabase-start.log; then
        log_success "Supabase services started successfully"
        return 0
    else
        log_error "Supabase startup failed"
        log_info "Check logs at /tmp/supabase-start.log for details"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# SERENA MCP SETUP FOR CLAUDE CODE
# -----------------------------------------------------------------------------

setup_mcp_servers() {
    log_info "Configuring Serena MCP for Claude Code..."

    # Use the pre-checked Claude availability
    if [[ "$CLAUDE_AVAILABLE" != "true" ]]; then
        log_warn "Claude Code not found - skipping Serena MCP setup"
        return 0
    fi

    # Check if Serena is already configured
    if claude mcp list 2>/dev/null | grep -q "serena"; then
        log_success "Serena MCP already configured"
        return 0
    fi

    # Add Serena MCP server for semantic code analysis
    log_info "Adding Serena semantic code analysis..."
    if claude mcp add serena -- uvx --from git+https://github.com/oraios/serena \
        serena start-mcp-server --context ide-assistant --project "$PROJECT_ROOT" &>/dev/null; then
        log_success "Serena MCP configured successfully"
        log_info "Use 'claude mcp list' to verify connection"
    else
        log_warn "Failed to configure Serena MCP"
        log_info "Configure manually with:"
        log_info "  claude mcp add serena -- uvx --from git+https://github.com/oraios/serena \\"
        log_info "    serena start-mcp-server --context ide-assistant --project $PROJECT_ROOT"
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

    # Use the pre-checked Claude availability
    if [[ "$CLAUDE_AVAILABLE" == "true" ]]; then
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