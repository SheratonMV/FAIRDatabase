#!/bin/bash
set -e

echo "🔧 Setting up MCP servers for Claude Code..."

# Check if Claude Code is installed
if ! command -v claude &> /dev/null; then
    echo "⚠️  Claude Code is not installed. Please install it first."
    exit 1
fi

# Setup directory for the project
PROJECT_DIR="/workspaces/FAIRDatabase"

# Configure Serena MCP server for semantic code analysis
echo "🔍 Configuring Serena MCP server..."
cd "$PROJECT_DIR"

# Check if uv is available (installed via devcontainer features)
if command -v uv &> /dev/null; then
    echo "✅ uv is available"

    # Add Serena MCP server to Claude Code
    claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project "$PROJECT_DIR" || {
        echo "⚠️  Failed to add Serena MCP. You can add it manually later with:"
        echo "    claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project \$(pwd)"
    }
else
    echo "⚠️  uv is not available. Installing it first..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source "$HOME/.cargo/env"

    if command -v uv &> /dev/null; then
        claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project "$PROJECT_DIR"
    else
        echo "❌ Failed to install uv. Please install it manually."
        exit 1
    fi
fi

# Install Python language server for better code analysis
echo "📦 Installing Python language server..."
uv pip install python-lsp-server[all] || pip install python-lsp-server[all]

# Install additional language servers if needed
echo "📦 Installing TypeScript language server..."
npm install -g typescript typescript-language-server

# List configured MCP servers
echo ""
echo "📋 Configured MCP servers:"
claude mcp list 2>/dev/null || echo "No MCP servers configured yet."

echo ""
echo "✅ MCP setup complete!"
echo ""
echo "📚 Usage tips:"
echo "  - To check MCP servers: claude mcp list"
echo "  - To remove a server: claude mcp remove <server-name>"
echo "  - To check Claude Code status: claude doctor"
echo ""
echo "🔍 Serena MCP provides semantic code tools:"
echo "  - Code navigation and understanding"
echo "  - Symbol-based editing"
echo "  - Efficient codebase exploration"
echo ""