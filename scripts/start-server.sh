#!/bin/bash
set -e
export PATH="$HOME/.local/bin:$PATH"

# Kill any existing processes on port 3001
fuser -k 3001/tcp 2>/dev/null || true
sleep 1

cd /opt/speakup/server

# Ensure deps are installed
uv sync

# Start server
nohup uv run python main.py > /tmp/speakup.log 2>&1 &
echo "Server started (PID $!)"
sleep 4

# Verify
curl -s http://localhost:3001/api/auth/login -X POST \
  -H 'Content-Type: application/json' \
  -d '{"phone":"13800138000"}'
echo ""
echo "Done"
