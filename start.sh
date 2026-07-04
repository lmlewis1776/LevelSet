#!/bin/bash
# LevelSet — Startup Script
cd "$(dirname "$0")"
source venv/bin/activate
gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120 app:app
