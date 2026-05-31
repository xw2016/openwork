#!/bin/bash
cd /home/cy/openwork/backend
.venv/bin/pip install fastapi 2>&1
echo "EXIT=$?"
.venv/bin/pip show fastapi 2>&1
echo "SHOW_EXIT=$?"
