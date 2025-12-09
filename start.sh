#!/bin/bash
# =============================================================================
# Lab Report Extraction System - Local Development Start Script
# =============================================================================
# This script starts all services for local development, mirroring docker-compose.
# For production, use: docker-compose up --build
#
# Services started:
#   - Redis (checks external)
#   - PostgreSQL (checks external)
#   - Backend (FastAPI on port 6000)
#   - Worker (RQ worker for background tasks)
#   - Frontend (Streamlit on port 8501)
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration (matching docker-compose defaults)
REDIS_URL="${REDIS__URL:-redis://localhost:6379/0}"
DB_PASSWORD="${DB_PASSWORD:-labextract2024}"
DATABASE_URL="${DATABASE__URL:-postgresql://postgres:${DB_PASSWORD}@localhost:5432/lab_extraction}"
BACKEND_PORT=6000
FRONTEND_PORT=8501

# PIDs for cleanup
WORKER_PID=""
BACKEND_PID=""
FRONTEND_PID=""

echo ""
echo -e "${BLUE}🧬 Starting Enterprise Lab Report Extraction System...${NC}"
echo "=================================================="
echo ""

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Shutting down services...${NC}"
    
    if [ -n "$FRONTEND_PID" ] && kill -0 $FRONTEND_PID 2>/dev/null; then
        echo "   Stopping Frontend (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    
    if [ -n "$BACKEND_PID" ] && kill -0 $BACKEND_PID 2>/dev/null; then
        echo "   Stopping Backend (PID: $BACKEND_PID)..."
        kill $BACKEND_PID 2>/dev/null || true
    fi
    
    if [ -n "$WORKER_PID" ] && kill -0 $WORKER_PID 2>/dev/null; then
        echo "   Stopping Worker (PID: $WORKER_PID)..."
        kill $WORKER_PID 2>/dev/null || true
    fi
    
    # Wait a moment for graceful shutdown
    sleep 2
    
    # Force kill if still running
    for pid in $FRONTEND_PID $BACKEND_PID $WORKER_PID; do
        if [ -n "$pid" ] && kill -0 $pid 2>/dev/null; then
            kill -9 $pid 2>/dev/null || true
        fi
    done
    
    echo -e "${GREEN}✅ All services stopped.${NC}"
    exit 0
}

wait_for_service() {
    local name=$1
    local url=$2
    local max_attempts=${3:-30}
    local attempt=1
    
    echo -n "   Waiting for $name to be ready"
    while [ $attempt -le $max_attempts ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -n "."
        sleep 1
        ((attempt++))
    done
    echo -e " ${RED}✗${NC}"
    return 1
}

check_port() {
    local port=$1
    if lsof -i :$port > /dev/null 2>&1; then
        return 0
    fi
    return 1
}

# Set up trap for cleanup
trap cleanup EXIT INT TERM

# -----------------------------------------------------------------------------
# Environment Setup
# -----------------------------------------------------------------------------
echo -e "${BLUE}📋 Checking Environment...${NC}"

# Check for .env file
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "   ${YELLOW}⚠️  Created .env file from template.${NC}"
        echo "   Please edit .env and add your GEMINI_API_KEY."
        echo ""
        read -p "   Press Enter after updating .env, or Ctrl+C to cancel..."
    else
        echo -e "   ${RED}❌ Error: No .env or .env.example file found.${NC}"
        exit 1
    fi
else
    echo -e "   ${GREEN}✓${NC} .env file found"
fi

# Load environment variables (safely, without executing values)
if [ -f .env ]; then
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ $key =~ ^#.*$ ]] && continue
        [[ -z $key ]] && continue
        # Remove any surrounding quotes from value
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        # Export the variable
        export "$key=$value"
    done < .env
fi

# Check if GEMINI_API_KEY is set
if grep -q "your_gemini_api_key_here" .env 2>/dev/null || [ -z "$GEMINI__API_KEY" ]; then
    echo -e "   ${YELLOW}⚠️  Warning: GEMINI__API_KEY appears to be missing or using placeholder.${NC}"
    echo "   Please update .env with your actual API key."
    echo ""
    read -p "   Press Enter to continue anyway, or Ctrl+C to cancel..."
else
    echo -e "   ${GREEN}✓${NC} GEMINI__API_KEY is set"
fi

echo ""

# -----------------------------------------------------------------------------
# Python Environment
# -----------------------------------------------------------------------------
echo -e "${BLUE}🐍 Setting up Python Environment...${NC}"

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "   Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate
echo -e "   ${GREEN}✓${NC} Virtual environment activated"

# Install dependencies
echo "   Installing dependencies..."
pip install -q -r requirements.txt
echo -e "   ${GREEN}✓${NC} Dependencies installed"

echo ""

# -----------------------------------------------------------------------------
# External Services Check (matching docker-compose dependencies)
# -----------------------------------------------------------------------------
echo -e "${BLUE}🔍 Checking External Services...${NC}"

# Check Redis (similar to docker-compose healthcheck)
echo -n "   Redis: "
if command -v redis-cli &> /dev/null; then
    if redis-cli ping &> /dev/null; then
        echo -e "${GREEN}✓ running${NC}"
    else
        echo -e "${YELLOW}not running${NC}"
        echo ""
        echo -e "   ${YELLOW}Redis is not running on localhost:6379${NC}"
        echo "   Start with one of:"
        echo "     - redis-server"
        echo "     - brew services start redis"
        echo "     - docker run -d -p 6379:6379 --name lab_redis redis:7-alpine"
        echo ""
        read -p "   Press Enter when Redis is running, or Ctrl+C to cancel..."
        
        # Verify Redis is now running
        if ! redis-cli ping &> /dev/null; then
            echo -e "   ${RED}❌ Redis still not responding. Please start Redis and try again.${NC}"
            exit 1
        fi
    fi
else
    echo -e "${YELLOW}redis-cli not found${NC}"
    echo "   Install with: brew install redis (macOS) or apt-get install redis (Linux)"
    echo "   Or use Docker: docker run -d -p 6379:6379 --name lab_redis redis:7-alpine"
fi

# Check PostgreSQL (matching docker-compose postgres service)
echo -n "   PostgreSQL: "
if command -v psql &> /dev/null || command -v pg_isready &> /dev/null; then
    if pg_isready -h localhost -p 5432 -U postgres &> /dev/null; then
        echo -e "${GREEN}✓ running${NC}"
        
        # Check if database exists
        if PGPASSWORD=$DB_PASSWORD psql -h localhost -U postgres -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw lab_extraction; then
            echo -e "   ${GREEN}✓${NC} Database 'lab_extraction' exists"
        else
            echo -e "   ${YELLOW}Creating database 'lab_extraction'...${NC}"
            PGPASSWORD=$DB_PASSWORD createdb -h localhost -U postgres lab_extraction 2>/dev/null || true
        fi
    else
        echo -e "${YELLOW}not running${NC}"
        echo ""
        echo -e "   ${YELLOW}PostgreSQL is not running on localhost:5432${NC}"
        echo "   Start with one of:"
        echo "     - brew services start postgresql"
        echo "     - docker run -d -p 5432:5432 --name lab_postgres \\"
        echo "         -e POSTGRES_DB=lab_extraction \\"
        echo "         -e POSTGRES_USER=postgres \\"
        echo "         -e POSTGRES_PASSWORD=$DB_PASSWORD \\"
        echo "         postgres:15-alpine"
        echo ""
        read -p "   Press Enter when PostgreSQL is running, or Ctrl+C to cancel..."
    fi
else
    echo -e "${YELLOW}psql/pg_isready not found${NC}"
    echo "   PostgreSQL client tools not installed."
    echo "   Install with: brew install postgresql (macOS)"
    echo "   Or use Docker for the database."
fi

echo ""

# -----------------------------------------------------------------------------
# Directory Setup
# -----------------------------------------------------------------------------
echo -e "${BLUE}📁 Setting up Directories...${NC}"
mkdir -p storage/lab-reports
mkdir -p logs
echo -e "   ${GREEN}✓${NC} storage/lab-reports"
echo -e "   ${GREEN}✓${NC} logs"

echo ""

# -----------------------------------------------------------------------------
# Export Environment Variables (matching docker-compose environment)
# -----------------------------------------------------------------------------
echo -e "${BLUE}🔧 Configuring Environment...${NC}"

export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}."
export REDIS__URL="$REDIS_URL"
export DATABASE__URL="$DATABASE_URL"

# Set defaults matching docker-compose
export GEMINI__MODEL="${GEMINI__MODEL:-gemma-3-27b-it}"
export GEMINI__RATE_LIMIT="${GEMINI__RATE_LIMIT:-10}"
export PROCESSING__MAX_RETRIES="${PROCESSING__MAX_RETRIES:-3}"
export STANDARDIZATION__FUZZY_THRESHOLD="${STANDARDIZATION__FUZZY_THRESHOLD:-0.85}"
export STANDARDIZATION__LLM_FALLBACK="${STANDARDIZATION__LLM_FALLBACK:-true}"

# Override API_URL for local development (not Docker)
export API_URL="http://localhost:$BACKEND_PORT/api/v1"

echo -e "   ${GREEN}✓${NC} Environment variables configured"
echo ""

# -----------------------------------------------------------------------------
# Start Services (matching docker-compose service order)
# -----------------------------------------------------------------------------
echo -e "${BLUE}🚀 Starting Services...${NC}"
echo ""

# Check if ports are available
if check_port $BACKEND_PORT; then
    echo -e "   ${RED}❌ Port $BACKEND_PORT is already in use.${NC}"
    echo "   Please stop any service using this port and try again."
    exit 1
fi

if check_port $FRONTEND_PORT; then
    echo -e "   ${RED}❌ Port $FRONTEND_PORT is already in use.${NC}"
    echo "   Please stop any service using this port and try again."
    exit 1
fi

# Start Worker (matching docker-compose worker service)
echo -e "   ${BLUE}[1/3]${NC} Starting Worker..."
rq worker lab_reports --url "$REDIS_URL" > logs/worker.log 2>&1 &
WORKER_PID=$!
echo -e "         PID: $WORKER_PID | Log: logs/worker.log"

# Give worker a moment to start
sleep 2

# Verify worker is running
if ! kill -0 $WORKER_PID 2>/dev/null; then
    echo -e "   ${RED}❌ Worker failed to start. Check logs/worker.log${NC}"
    exit 1
fi
echo -e "         ${GREEN}✓ Worker started${NC}"

# Start Backend (matching docker-compose backend service)
echo ""
echo -e "   ${BLUE}[2/3]${NC} Starting Backend..."
uvicorn backend.main:app --host 0.0.0.0 --port $BACKEND_PORT > logs/backend.log 2>&1 &
BACKEND_PID=$!
echo -e "         PID: $BACKEND_PID | Log: logs/backend.log"

# Health check for backend (matching docker-compose healthcheck)
if ! wait_for_service "Backend" "http://localhost:$BACKEND_PORT/docs" 30; then
    echo -e "   ${RED}❌ Backend failed to start. Check logs/backend.log${NC}"
    exit 1
fi

# Start Frontend (matching docker-compose frontend service)
echo ""
echo -e "   ${BLUE}[3/3]${NC} Starting Frontend..."
echo ""

# =============================================================================
# Startup Complete
# =============================================================================
echo "=================================================="
echo -e "${GREEN}✅ All services started successfully!${NC}"
echo "=================================================="
echo ""
echo "   📊 Frontend:     http://localhost:$FRONTEND_PORT"
echo "   📡 Backend API:  http://localhost:$BACKEND_PORT"
echo "   📚 API Docs:     http://localhost:$BACKEND_PORT/docs"
echo "   📖 ReDoc:        http://localhost:$BACKEND_PORT/redoc"
echo ""
echo "   📋 Logs:"
echo "      - Backend: logs/backend.log"
echo "      - Worker:  logs/worker.log"
echo ""
echo "   🛑 Press Ctrl+C to stop all services"
echo "=================================================="
echo ""

# Start Streamlit in foreground (keeps script running)
streamlit run frontend_app/main.py --server.port $FRONTEND_PORT --server.address 0.0.0.0
