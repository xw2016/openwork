#!/bin/bash
set -e
cd /home/cy/openwork/backend

# Install python3.14-venv if needed
sudo apt-get update -qq && sudo apt-get install -y -qq python3.14-venv 2>&1

# Recreate venv
rm -rf .venv
/usr/bin/python3 -m venv .venv

# Upgrade pip
.venv/bin/python -m pip install --upgrade pip -q

# Install all dependencies
.venv/bin/python -m pip install \
  fastapi \
  "uvicorn[standard]" \
  python-multipart \
  "sqlalchemy[asyncio]" \
  asyncpg \
  alembic \
  redis \
  "python-jose[cryptography]" \
  "passlib[bcrypt]" \
  bcrypt \
  pydantic-settings \
  structlog \
  pycryptodome \
  httpx \
  pytest \
  pytest-asyncio \
  -q

echo "===INSTALL COMPLETE==="
.venv/bin/python -m pip list 2>/dev/null
