#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo -e "\n${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    India Quant Fund — Bootstrap      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}\n"

# 1. Check Python
log_info "Checking Python version..."
PYTHON_VER=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED="3.10"
if python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)"; then
    log_ok "Python $PYTHON_VER detected"
else
    log_error "Python >= 3.10 required. Found: $PYTHON_VER"
    exit 1
fi

# 2. Check Poetry
log_info "Checking Poetry..."
if command -v poetry &>/dev/null; then
    log_ok "Poetry $(poetry --version | awk '{print $3}') found"
else
    log_warn "Poetry not found. Installing..."
    curl -sSL https://install.python-poetry.org | python3 -
fi

# 3. Install Python deps
log_info "Installing Python dependencies..."
poetry install --without dev
log_ok "Dependencies installed"

# 4. Check .env
log_info "Checking environment configuration..."
if [ ! -f .env ]; then
    cp .env.example .env
    log_warn ".env created from .env.example — please fill in your API keys before running"
else
    log_ok ".env found"
fi

# 5. Create required directories
log_info "Creating directories..."
mkdir -p data/db logs reports
log_ok "Directories ready"

# 6. Initialise DuckDB schema
log_info "Initialising database schema..."
python3 -c "
from data.storage.db import db
import duckdb
with open('data/storage/schema.sql') as f:
    db.get_connection().executescript(f.read())
print('Schema applied')
"
log_ok "Database initialised"

# 7. Validate setup
log_info "Validating configuration..."
python3 scripts/validate_setup.py

echo -e "\n${GREEN}Bootstrap complete!${NC}"
echo -e "Next steps:"
echo -e "  1. Fill in ${YELLOW}.env${NC} with your API keys (Dhan, Shoonya, DeepSeek, Gemini, Telegram)"
echo -e "  2. Run ${YELLOW}python scripts/backfill.py${NC} to load 5 years of historical data"
echo -e "  3. Run ${YELLOW}python -m backtest.runner --walk-forward${NC} to validate strategies"
echo -e "  4. Start with ${YELLOW}docker-compose -f infrastructure/docker-compose.yml up${NC}"
echo -e "     or ${YELLOW}uvicorn api.main:app --reload${NC} for API-only development\n"
