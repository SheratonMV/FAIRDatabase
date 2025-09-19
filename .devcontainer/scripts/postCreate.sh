#!/bin/bash
set -e

echo "🚀 Running postCreate setup for FAIRDatabase..."

# Install Node dependencies
echo "📦 Installing Node dependencies..."
if [ -f "package.json" ]; then
    npm install
fi

# Install Supabase CLI
echo "📦 Installing Supabase CLI..."
npm install -D supabase

# Install Claude Code CLI
echo "🤖 Installing Claude Code CLI..."
npm install -g @anthropic-ai/claude-code || {
    echo "⚠️  npm install failed, trying native installer..."
    curl -fsSL https://claude.ai/install.sh | bash
}

# Verify Claude Code installation
if command -v claude &> /dev/null; then
    echo "✅ Claude Code installed successfully"
    claude --version
else
    echo "⚠️  Claude Code installation failed. You can install it manually later."
fi

# Install Python dependencies
echo "🐍 Setting up Python environment..."
cd backend

# Create virtual environment with uv
echo "📦 Creating Python virtual environment..."
uv venv

# Activate and install dependencies
if [ -f "requirements.txt" ]; then
    echo "📚 Installing Python dependencies..."
    uv pip install -r requirements.txt
fi

if [ -f "requirements-dev.txt" ]; then
    echo "📚 Installing development dependencies..."
    uv pip install -r requirements-dev.txt
fi

# Set up git configuration
echo "🔧 Configuring Git..."
git config --global --add safe.directory /workspaces/FAIRDatabase

# Create .env file from sample if it doesn't exist
if [ ! -f ".env" ] && [ -f ".env.sample" ]; then
    echo "🔐 Creating .env file from sample..."
    cp .env.sample .env
fi

cd ..

echo "✅ postCreate setup complete!"