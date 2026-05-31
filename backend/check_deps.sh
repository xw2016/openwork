#!/bin/bash
.venv/bin/pip list --format=columns 2>/dev/null | head -40
echo "---DONE---"
