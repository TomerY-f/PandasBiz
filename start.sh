#!/bin/zsh
# (Re)starts PandasBiz: API on :8000 and web app on :5173, then opens the browser.
# Usage:  ./start.sh          Logs: backend/data/api.log, backend/data/web.log
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Stopping anything on ports 8000 / 5173..."
for port in 8000 5173; do
  pids=$(lsof -ti tcp:$port -sTCP:LISTEN 2>/dev/null)
  [ -n "$pids" ] && kill $pids 2>/dev/null
done
sleep 1

mkdir -p "$ROOT/backend/data"
echo "Starting API..."
(cd "$ROOT/backend" && nohup .venv/bin/python -m uvicorn app.main:app --reload --port 8000 > data/api.log 2>&1 &)
echo "Starting web app..."
(cd "$ROOT/frontend" && nohup npm run dev -- --port 5173 > ../backend/data/web.log 2>&1 &)

echo -n "Waiting for the app to come up (first start after OneDrive sync can take a minute)"
for i in {1..90}; do
  if curl -s -m 2 http://localhost:5173/api/health | grep -q ok; then
    echo " ready."
    open "http://localhost:5173"
    exit 0
  fi
  echo -n "."
  sleep 2
done
echo " still starting; check backend/data/api.log and backend/data/web.log"
exit 1
