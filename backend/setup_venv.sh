#!/bin/bash
set -e
cd /home/cy/openwork/backend

# Remove old venv
rm -rf .venv

# Create fresh venv
/usr/bin/python3 -m venv .venv

# Upgrade pip
.venv/bin/python -m pip install --upgrade pip -q

# Install all dependencies
.venv/bin/python -m pip install \
  fastapi \
  uvicorn[standard] \
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
.venv/bin/python -m pip list 2>/dev/null | wc -l
echo "packages installed"
