#!/bin/bash
# Setup development environment on container creation
set -e

echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║       🔧 Setting up FAIRDatabase Development Environment          ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""

# Setup Python environment with uv
if [ -f "backend/pyproject.toml" ]; then
    echo "🐍 Setting up Python environment..."
    cd backend
    uv sync --all-groups
    cd ..
    echo "✅ Python environment ready"
fi

# Install PostgreSQL client tools
echo "🐘 Installing PostgreSQL client tools..."
sudo apt update && sudo apt install -y postgresql-client
echo "✅ PostgreSQL client tools installed"

# Setup environment files from templates
echo "⚙️ Setting up environment configuration..."
if [ ! -f "backend/.env" ]; then
    cp backend/.env.example backend/.env
    echo "✅ Created backend/.env from template"
    echo "⚠️  Review and update values in backend/.env if needed"
else
    echo "ℹ️ backend/.env already exists"
fi

if [ ! -f "backend/tests/.env.test" ]; then
    cp backend/tests/.env.test.example backend/tests/.env.test
    echo "✅ Created backend/tests/.env.test from template"
else
    echo "ℹ️ backend/tests/.env.test already exists"
fi

# Update npm to latest version
echo "📦 Updating npm to latest version..."
npm install -g npm@latest
echo "✅ npm updated"

# Install Supabase CLI as dev dependency
echo "🔧 Installing Supabase CLI..."
npm install supabase --save-dev
echo "✅ Supabase CLI installed"

# Initialize Supabase for local development (if not already initialized)
if [ ! -d "supabase" ]; then
    echo "🔧 Initializing Supabase for local development..."
    npx supabase init
    echo "✅ Supabase initialized"
else
    echo "ℹ️ Supabase already initialized"
fi

# Display completion message
echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║                       🚀 SETUP COMPLETE!                          ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "┌─── Next Steps ──────────────────────────────────────────────────┐"
echo "│                                                                 │"
echo "│  💾 Start Supabase:                                             │"
echo "│     npx supabase start                                          │"
echo "│                                                                 │"
echo "│  🧪 Start Flask application:                                    │"
echo "│     cd backend                                                  │"
echo "│     uv run flask run                                            │"
echo "│                                                                 │"
echo "│  🔬 Run tests:                                                  │"
echo "│     cd backend                                                  │"
echo "│     uv run pytest                                               │"
echo "│                                                                 │"
echo "└─────────────────────────────────────────────────────────────────┘"
echo ""