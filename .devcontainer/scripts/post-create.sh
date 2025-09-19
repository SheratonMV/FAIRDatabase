#!/bin/bash

# =============================================================================
# post-create.sh - Initial container setup
# Runs once when the container is first created
# Responsibility: Install dependencies and perform one-time setup
# =============================================================================

# Source shared utilities (provides error handling and common functions)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "${SCRIPT_DIR}/utils.sh"

# -----------------------------------------------------------------------------
# MAIN SETUP PROCESS
# -----------------------------------------------------------------------------

main() {
    log_section "🚀 FAIRDatabase DevContainer - Initial Setup"

    # Validate we're in the right environment
    validate_environment || exit 1

    # Each setup step is independent and can fail fast
    setup_node_environment
    setup_python_environment
    setup_development_tools
    setup_git_configuration
    setup_environment_files

    log_section "✅ Initial Setup Complete"
    log_info "Container is ready for development"
}

# -----------------------------------------------------------------------------
# NODE.JS ENVIRONMENT SETUP
# -----------------------------------------------------------------------------

setup_node_environment() {
    log_info "Setting up Node.js environment..."

    # Change to project root for Node operations
    cd "$PROJECT_ROOT" || exit 1

    # Install project dependencies if package.json exists
    if [[ -f "package.json" ]]; then
        log_info "Installing Node.js dependencies..."
        npm install || {
            log_error "Failed to install Node.js dependencies"
            exit 1
        }
        log_success "Node.js dependencies installed"
    else
        log_debug "No package.json found, skipping Node dependency installation"
    fi

    # Install Supabase CLI as dev dependency
    log_info "Installing Supabase CLI..."
    npm install -D supabase || {
        log_error "Failed to install Supabase CLI"
        log_info "You can install it manually with: npm install -D supabase"
        exit 1
    }
    log_success "Supabase CLI installed"
}

# -----------------------------------------------------------------------------
# PYTHON ENVIRONMENT SETUP
# -----------------------------------------------------------------------------

setup_python_environment() {
    log_info "Setting up Python environment..."

    # Change to backend directory
    cd "$BACKEND_DIR" || {
        log_error "Backend directory not found: $BACKEND_DIR"
        exit 1
    }

    # Ensure uv is available
    if ! command_exists "uv"; then
        log_error "uv is not available - required for Python dependency management"
        log_info "Install uv with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi

    # Sync all Python dependencies using uv
    log_info "Syncing Python dependencies with uv..."
    uv sync --all-groups || {
        log_error "Failed to sync Python dependencies"
        log_info "Check pyproject.toml for dependency issues"
        exit 1
    }
    log_success "Python dependencies synced"

    # Return to project root
    cd "$PROJECT_ROOT" || exit 1
}

# -----------------------------------------------------------------------------
# DEVELOPMENT TOOLS SETUP
# -----------------------------------------------------------------------------

setup_development_tools() {
    log_info "Setting up development tools..."

    # Install Claude Code CLI
    install_claude_code || {
        log_warn "Claude Code installation failed - some AI features will be unavailable"
        log_info "You can install it manually later with: npm install -g @anthropic-ai/claude-code"
        # Don't exit - Claude Code is optional
    }
}

# -----------------------------------------------------------------------------
# GIT CONFIGURATION
# -----------------------------------------------------------------------------

setup_git_configuration() {
    log_info "Configuring Git..."

    # Mark directory as safe for Git operations
    git config --global --add safe.directory "$PROJECT_ROOT" || {
        log_warn "Failed to configure Git safe directory"
        # Non-fatal - continue setup
    }

    # Set up useful Git aliases (optional)
    git config --global alias.st "status --short" 2>/dev/null || true
    git config --global alias.co "checkout" 2>/dev/null || true
    git config --global alias.br "branch" 2>/dev/null || true

    log_success "Git configured"
}

# -----------------------------------------------------------------------------
# ENVIRONMENT FILES SETUP
# -----------------------------------------------------------------------------

setup_environment_files() {
    log_info "Setting up environment files..."

    # Change to backend directory for .env setup
    cd "$BACKEND_DIR" || exit 1

    # Create .env from sample if needed
    if [[ ! -f ".env" ]] && [[ -f ".env.sample" ]]; then
        log_info "Creating .env file from sample..."
        safe_copy ".env.sample" ".env"
        log_success "Environment file created - please update with your values"
    elif [[ -f ".env" ]]; then
        log_debug "Environment file already exists"
    else
        log_warn "No .env.sample found - create .env manually if needed"
    fi

    # Return to project root
    cd "$PROJECT_ROOT" || exit 1
}

# -----------------------------------------------------------------------------
# EXECUTE MAIN FUNCTION
# -----------------------------------------------------------------------------

main "$@"