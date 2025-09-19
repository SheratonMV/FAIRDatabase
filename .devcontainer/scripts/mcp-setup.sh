#!/bin/bash

# =============================================================================
# mcp-setup.sh - MCP (Model Context Protocol) Server Configuration
# Responsibility: Configure AI assistance tools for the development environment
# =============================================================================

# Source shared utilities
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "${SCRIPT_DIR}/utils.sh"

# -----------------------------------------------------------------------------
# CONSTANTS
# -----------------------------------------------------------------------------

readonly SERENA_REPO="git+https://github.com/oraios/serena"
readonly PYLSP_PACKAGE="python-lsp-server[all]"
readonly TS_PACKAGES="typescript typescript-language-server"

# -----------------------------------------------------------------------------
# MAIN SETUP PROCESS
# -----------------------------------------------------------------------------

main() {
    log_section "🤖 MCP Server Configuration"

    # Validate prerequisites
    validate_prerequisites || exit 1

    # Configure MCP servers
    configure_serena_server
    install_language_servers

    # Verify configuration
    verify_mcp_configuration

    log_success "MCP configuration complete"
}

# -----------------------------------------------------------------------------
# PREREQUISITE VALIDATION
# -----------------------------------------------------------------------------

validate_prerequisites() {
    log_info "Validating prerequisites..."

    # Claude Code is required
    if ! check_claude_code; then
        log_error "Claude Code CLI is required but not installed"
        log_info "Install with: npm install -g @anthropic-ai/claude-code"
        return 1
    fi

    # uv is required for Serena
    if ! ensure_uv_available; then
        return 1
    fi

    log_success "Prerequisites validated"
    return 0
}

ensure_uv_available() {
    if command_exists "uv"; then
        log_debug "uv is already available"
        return 0
    fi

    log_warn "uv not found - installing..."

    # Install uv using official installer
    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
        # Source cargo environment to make uv available
        [[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env"

        if command_exists "uv"; then
            log_success "uv installed successfully"
            return 0
        fi
    fi

    log_error "Failed to install uv"
    log_info "Install manually from: https://github.com/astral-sh/uv"
    return 1
}

# -----------------------------------------------------------------------------
# SERENA MCP SERVER CONFIGURATION
# -----------------------------------------------------------------------------

configure_serena_server() {
    log_info "Configuring Serena semantic code analysis server..."

    cd "$PROJECT_ROOT" || exit 1

    # Check if Serena is already configured
    if claude mcp list 2>/dev/null | grep -q "serena"; then
        log_success "Serena is already configured"
        return 0
    fi

    # Add Serena MCP server
    local serena_cmd="uvx --from ${SERENA_REPO} serena start-mcp-server"
    serena_cmd="${serena_cmd} --context ide-assistant --project ${PROJECT_ROOT}"

    if claude mcp add serena -- $serena_cmd; then
        log_success "Serena MCP server configured"
        log_info "Serena provides semantic code navigation and editing"
    else
        log_warn "Failed to configure Serena MCP server"
        log_info "Configure manually with:"
        log_info "  claude mcp add serena -- ${serena_cmd}"
        # Non-fatal - continue with other servers
    fi
}

# -----------------------------------------------------------------------------
# LANGUAGE SERVER INSTALLATION
# -----------------------------------------------------------------------------

install_language_servers() {
    log_info "Installing language servers for enhanced code analysis..."

    install_python_lsp
    install_typescript_lsp
}

install_python_lsp() {
    log_debug "Installing Python Language Server..."

    # Try to install in virtual environment first
    if is_venv_active; then
        if pip install --quiet "${PYLSP_PACKAGE}" 2>/dev/null; then
            log_success "Python LSP installed in virtual environment"
            return 0
        fi
    fi

    # Try using venv pip directly
    if [[ -x "${VENV_PATH}/bin/pip" ]]; then
        if "${VENV_PATH}/bin/pip" install --quiet "${PYLSP_PACKAGE}" 2>/dev/null; then
            log_success "Python LSP installed via venv pip"
            return 0
        fi
    fi

    # Fall back to global installation
    log_debug "Installing Python LSP globally..."
    if pip install --quiet "${PYLSP_PACKAGE}" 2>/dev/null; then
        log_success "Python LSP installed globally"
    else
        log_warn "Failed to install Python LSP"
        log_info "Install manually with: pip install ${PYLSP_PACKAGE}"
    fi
}

install_typescript_lsp() {
    log_debug "Installing TypeScript Language Server..."

    if ! command_exists "npm"; then
        log_warn "npm not available - skipping TypeScript LSP installation"
        return 1
    fi

    if npm list -g typescript typescript-language-server &>/dev/null; then
        log_debug "TypeScript LSP already installed"
        return 0
    fi

    if npm install -g --quiet ${TS_PACKAGES} 2>/dev/null; then
        log_success "TypeScript LSP installed"
    else
        log_warn "Failed to install TypeScript LSP"
        log_info "Install manually with: npm install -g ${TS_PACKAGES}"
    fi
}

# -----------------------------------------------------------------------------
# CONFIGURATION VERIFICATION
# -----------------------------------------------------------------------------

verify_mcp_configuration() {
    log_info "Verifying MCP configuration..."

    # List configured MCP servers
    if output=$(claude mcp list 2>/dev/null); then
        log_success "MCP servers configured:"
        echo "$output" | while IFS= read -r line; do
            echo "  $line"
        done
    else
        log_warn "No MCP servers configured or Claude Code not responding"
    fi

    # Display usage information
    echo ""
    log_info "MCP Management Commands:"
    echo "  claude mcp list              # List configured servers"
    echo "  claude mcp remove <name>     # Remove a server"
    echo "  claude doctor                # Check Claude Code health"
    echo ""

    if claude mcp list 2>/dev/null | grep -q "serena"; then
        log_info "Serena Features:"
        echo "  - Semantic code navigation (find symbols, references)"
        echo "  - Symbol-level editing (edit functions, classes directly)"
        echo "  - Efficient codebase exploration (avoid reading entire files)"
        echo ""
    fi
}

# -----------------------------------------------------------------------------
# EXECUTE MAIN FUNCTION
# -----------------------------------------------------------------------------

main "$@"