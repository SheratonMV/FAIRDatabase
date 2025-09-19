#!/bin/bash
set -e

echo "🎯 Running postStart setup for FAIRDatabase..."

# Check if Supabase is initialized
if [ ! -f "supabase/config.toml" ]; then
    echo "⚠️  Supabase not initialized. Initializing..."
    npx supabase init
fi

# Start Supabase services
echo "🚀 Starting Supabase services..."
if npx supabase status 2>/dev/null | grep -q "RUNNING"; then
    echo "✅ Supabase is already running"
else
    echo "📊 Starting Supabase (this may take a moment)..."
    npx supabase start || {
        echo "⚠️  Failed to start Supabase. You can start it manually with: npx supabase start"
        exit 0  # Don't fail the container start
    }
fi

# Display service URLs
echo ""
echo "🌐 Service URLs:"
echo "  - Flask Backend:    http://localhost:5000"
echo "  - Supabase Studio:  http://localhost:54321"
echo "  - Supabase API:     http://localhost:54323"
echo ""

# Check Python environment
echo "🐍 Python environment:"
python --version
echo ""

# Setup MCP servers for Claude Code
if [ -f "/workspaces/FAIRDatabase/.devcontainer/scripts/mcp-setup.sh" ]; then
    echo "🤖 Setting up MCP servers for Claude Code..."
    bash /workspaces/FAIRDatabase/.devcontainer/scripts/mcp-setup.sh || {
        echo "⚠️  MCP setup failed. You can run it manually later with:"
        echo "    .devcontainer/scripts/mcp-setup.sh"
    }
fi

# Display helpful commands
echo "📚 Helpful commands:"
echo "  - Run tests:        cd backend && pytest"
echo "  - Run linter:       ruff check ."
echo "  - Format code:      ruff format ."
echo "  - Start backend:    cd backend && python app.py"
echo ""
echo "🤖 Claude Code commands:"
echo "  - Get AI help:      claude"
echo "  - Check MCP:        claude mcp list"
echo "  - Check health:     claude doctor"
echo ""

echo "✅ postStart setup complete! Happy coding! 🎉"