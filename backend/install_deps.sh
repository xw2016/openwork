#!/bin/bash
cd /home/cy/openwork/backend
.venv/bin/pip install -q fastapi uvicorn sqlalchemy asyncpg alembic redis "python-jose[cryptography]" passlib[bcrypt] pydantic-settings structlog pycryptodome httpx pytest pytest-asyncio python-multipart 2>&1
echo "INSTALL_DONE exit=$?"
