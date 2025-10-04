#!/bin/bash
# Setup development environment on container creation
set -e

echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║       🔧 Setting up FAIRDatabase Development Environment          ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""

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

# Initialize Supabase for local development (if not already initialized)
if [ ! -d "supabase" ]; then
    echo "🔧 Initializing Supabase for local development..."
    npx supabase init
    echo "✅ Supabase initialized"
else
    echo "ℹ️ Supabase already initialized"
fi

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
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║                       🚀 SETUP COMPLETE!                          ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "┌─── Next Steps ──────────────────────────────────────────────────┐"
echo "│                                                                 │"
echo "│  🗄️ Start Supabase:                                             │"
echo "│     npx supabase start                                          │"
echo "│                                                                 │"
echo "│  🚀 Start Flask application:                                    │"
echo "│     cd backend                                                  │"
echo "│     uv run flask run                                            │"
echo "│                                                                 │"
echo "│  🌐 Application URLs:                                           │"
echo "│     • Flask Backend:    http://localhost:5000                   │"
echo "│     • Supabase Studio:  http://localhost:54321                  │"
echo "│     • API Gateway:      http://localhost:54323                  │"
echo "│                                                                 │"
echo "└─────────────────────────────────────────────────────────────────┘"
echo ""