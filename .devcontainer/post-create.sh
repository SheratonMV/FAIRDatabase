#!/bin/bash
# Setup development environment on container creation
set -e

echo "🔧 Setting up FAIRDatabase development environment..."

# Configure Git for safe directory and pull strategy
echo "📝 Configuring Git settings..."
git config --global --add safe.directory "${PWD}"
git config --global pull.rebase false
echo "✅ Git configured"

# Setup Python environment with uv
if [ -f "backend/pyproject.toml" ]; then
    echo "🐍 Setting up Python environment..."
    cd backend
    uv sync --all-groups
    cd ..
    echo "✅ Python environment ready"
fi

# Update npm to latest version
echo "📦 Updating npm to latest version..."
npm install -g npm@latest
echo "✅ npm updated"

# Install Supabase CLI for database management
echo "🗄️ Installing Supabase CLI..."
npm install supabase --save-dev
echo "✅ Supabase CLI installed"

# Install Claude Code CLI for AI assistance
echo "🤖 Installing Claude Code CLI..."
npm install -g @anthropic-ai/claude-code
echo "✅ Claude Code CLI installed"

# Configure Claude Code MCP for semantic code analysis
echo "⚙️ Configuring Claude Code MCP (Serena)..."
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project "$(pwd)"
echo "✅ Claude Code MCP configured"

# Display completion message
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "                  SETUP COMPLETE! 🚀                           "
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  ℹ️  Supabase will start automatically when the container starts"
echo "  ℹ️  Claude Code CLI is ready with Serena MCP integration"
echo ""