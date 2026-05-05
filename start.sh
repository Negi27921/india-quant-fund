#!/usr/bin/env bash
# Start the IQF backend + Cloudflare tunnel, then redeploy Vercel with the new URL.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DASHBOARD_DIR="$SCRIPT_DIR/dashboard"

echo "==> Killing any existing uvicorn / cloudflared..."
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
pkill -9 -f "uvicorn api.main" 2>/dev/null || true
pkill -9 -f "cloudflared tunnel" 2>/dev/null || true
sleep 1

echo "==> Starting FastAPI backend on port 8000..."
cd "$SCRIPT_DIR"
nohup uvicorn api.main:app --host 127.0.0.1 --port 8000 > /tmp/iqf_api.log 2>&1 &
API_PID=$!
echo "    PID: $API_PID"

# Wait for the API to be ready
for i in $(seq 1 15); do
  sleep 1
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/portfolio/summary', timeout=3)" 2>/dev/null; then
    echo "    API is up."
    break
  fi
  echo "    Waiting for API... ($i)"
done

echo "==> Starting Cloudflare tunnel..."
nohup cloudflared tunnel --url http://127.0.0.1:8000 > /tmp/cf_tunnel.log 2>&1 &
CF_PID=$!

echo "    Waiting for tunnel URL..."
CF_URL=""
for i in $(seq 1 20); do
  sleep 1
  CF_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/cf_tunnel.log 2>/dev/null | head -1)
  if [ -n "$CF_URL" ]; then break; fi
  echo "    Waiting... ($i)"
done

if [ -z "$CF_URL" ]; then
  echo "ERROR: Could not get Cloudflare tunnel URL. Check /tmp/cf_tunnel.log"
  exit 1
fi

echo "    Tunnel URL: $CF_URL"

echo "==> Updating Vercel VITE_API_URL..."
cd "$DASHBOARD_DIR"
vercel env rm VITE_API_URL production --yes 2>/dev/null || true
echo "$CF_URL" | vercel env add VITE_API_URL production

echo "==> Deploying to Vercel..."
vercel deploy --prod

echo ""
echo "============================"
echo " Dashboard: https://dashboard-two-plum-91.vercel.app"
echo " Backend:   http://127.0.0.1:8000"
echo " Tunnel:    $CF_URL"
echo "============================"
echo " API PID: $API_PID  |  Tunnel PID: $CF_PID"
echo " Logs:  /tmp/iqf_api.log  |  /tmp/cf_tunnel.log"
