#!/bin/bash
# =============================================================================
# Lab Report Extraction System - Local Development Start Script
# =============================================================================
# This script starts all services for local development.
# For production, use: docker-compose up --build
# =============================================================================

set -e

echo "🧬 Starting Enterprise Lab Report Extraction System..."
echo "=================================================="

# Check for .env file
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "⚠️  Created .env file from template."
        echo "   Please edit .env and add your GEMINI_API_KEY."
        echo ""
        read -p "Press Enter after updating .env, or Ctrl+C to cancel..."
    else
        echo "❌ Error: No .env or .env.example file found."
        exit 1
    fi
fi

# Check if GEMINI_API_KEY is set
if grep -q "your_gemini_api_key_here" .env 2>/dev/null; then
    echo "⚠️  Warning: GEMINI_API_KEY appears to be using placeholder value."
    echo "   Please update .env with your actual API key."
    echo ""
    read -p "Press Enter to continue anyway, or Ctrl+C to cancel..."
fi

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install -q -r requirements.txt

# Check Redis
echo "🔍 Checking Redis..."
if ! command -v redis-cli &> /dev/null; then
    echo "⚠️  redis-cli not found. Redis may not be installed."
    echo "   Install with: brew install redis (macOS) or apt-get install redis (Linux)"
fi

if ! redis-cli ping &> /dev/null; then
    echo "⚠️  Redis is not running on localhost:6379"
    echo "   Start Redis with: redis-server"
    echo "   Or using Docker: docker run -d -p 6379:6379 redis:7-alpine"
    echo ""
    read -p "Press Enter to continue when Redis is running, or Ctrl+C to cancel..."
fi

# Create storage directory
mkdir -p storage/lab-reports

# Export environment variables
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
export PYTHONPATH=$PYTHONPATH:.

# Start Worker in background
echo "🔧 Starting Worker..."
rq worker lab_reports --url redis://localhost:6379/0 > worker.log 2>&1 &
WORKER_PID=$!
echo "   Worker PID: $WORKER_PID"

# Start Backend in background
echo "🚀 Starting Backend..."
uvicorn backend.main:app --host 0.0.0.0 --port 6000 > backend.log 2>&1 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"

# Wait for backend to be ready
echo "⏳ Waiting for Backend to initialize..."
for i in {1..30}; do
    if curl -s http://localhost:6000/docs > /dev/null 2>&1; then
        echo "   Backend is ready!"
        break
    fi
    sleep 1
done

# Start Frontend
echo "🎨 Starting Frontend..."
echo ""
echo "=================================================="
echo "✅ System is starting up!"
echo ""
echo "   📊 Frontend:  http://localhost:8505"
echo "   📡 Backend:   http://localhost:6000"
echo "   📚 API Docs:  http://localhost:6000/docs"
echo ""
echo "   Logs: backend.log, worker.log"
echo "=================================================="
echo ""

# Cleanup on exit
trap "echo ''; echo 'Shutting down...'; kill $WORKER_PID $BACKEND_PID 2>/dev/null; exit 0" EXIT INT TERM

# Start Streamlit in foreground
streamlit run frontend_app/main.py --server.port 8501
