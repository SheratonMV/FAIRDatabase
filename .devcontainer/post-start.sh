#!/bin/bash
set -e

echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║            🚀 Starting Development Environment                    ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""

# Start Supabase
echo "🔄 Starting Supabase services..."
npx supabase start

# Create backend .env file (always create since it's not tracked in git)
echo "📝 Creating backend .env file..."
cat > /workspaces/FAIRDatabase/backend/.env << 'EOF'
# Auto-generated for local development
ENV=development
SECRET_KEY=dev-secret-key-for-local-testing
UPLOAD_FOLDER=./uploads

# Supabase Local Development
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU

# PostgreSQL Direct Connection
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=54322
POSTGRES_USER=postgres
POSTGRES_SECRET=postgres
POSTGRES_DB_NAME=postgres
EOF

echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║                    ✅ Environment Ready!                          ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "┌─── Quick Commands ──────────────────────────────────────────────┐"
echo "│                                                                 │"
echo "│  🔥 Start Flask:    cd backend && uv run flask run              │"
echo "│  🧪 Run tests:      cd backend && uv run pytest                 │"
echo "│                                                                 │"
echo "└─────────────────────────────────────────────────────────────────┘"
echo ""