#!/bin/bash
# One command to set up and run the Virtual KAM on your Mac.
#   ./start.sh            normal start (keeps your call history)
#   ./start.sh --reset    wipe calls and reload the mock sellers
#   ./start.sh --dev      run the web app in development mode (hot reload, slower)
# It asks for your three LiveKit values the first time, starts a local Postgres in
# Docker (OrbStack) if no DATABASE_URL is set, installs everything, makes the first
# Sarvam call, loads the mock sellers, then runs the voice agent and the web app.
set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"
ENV="$ROOT/agent/.env"

getv() { grep -E "^$1=" "$ENV" 2>/dev/null | head -1 | cut -d= -f2-; }
setv() {
  if grep -qE "^$1=" "$ENV" 2>/dev/null; then
    python3 - "$ENV" "$1" "$2" <<'PY'
import sys
path, key, val = sys.argv[1:4]
lines = open(path).read().splitlines()
out = [f"{key}={val}" if l.startswith(key + "=") else l for l in lines]
open(path, "w").write("\n".join(out) + "\n")
PY
  else
    echo "$1=$2" >> "$ENV"
  fi
}

echo "== 1/6 LiveKit keys =="
for key in LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET; do
  if [ -z "$(getv $key)" ]; then
    read -r -p "Paste $key (LiveKit Cloud > Settings > API keys): " val
    setv "$key" "$val"
  fi
done

echo "== 2/6 Database =="
if [ -z "$(getv DATABASE_URL)" ]; then
  if command -v docker >/dev/null 2>&1; then
    docker start kam-pg >/dev/null 2>&1 || docker run -d --name kam-pg -e POSTGRES_PASSWORD=kam -p 5544:5432 postgres:16 >/dev/null
    setv DATABASE_URL "postgresql://postgres:kam@localhost:5544/postgres"
    echo "Local Postgres running in Docker on port 5544."
    sleep 4
  else
    read -r -p "Docker not found. Paste a Postgres URL (for example from neon.tech): " val
    setv DATABASE_URL "$val"
  fi
elif echo "$(getv DATABASE_URL)" | grep -q "localhost:5544"; then
  docker start kam-pg >/dev/null 2>&1 || true
  sleep 2
fi

echo "== 3/6 Python packages =="
PY=python3
for c in python3.12 python3.13 python3.11 python3.10; do command -v $c >/dev/null 2>&1 && PY=$c && break; done
cd "$ROOT/agent"
[ -d .venv ] || $PY -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "== 4/6 Sarvam check, tests, mock sellers =="
[ -f hello_sarvam.wav ] || python hello_sarvam.py || echo "Sarvam call failed: check SARVAM_API_KEY in agent/.env"
python -m pytest -q
case " $* " in *" --reset "*) python -m brain.seed ;; *) python -m brain.seed --if-empty ;; esac

echo "== 5/6 Web app packages =="
cd "$ROOT/web"
{
  echo "DATABASE_URL=$(getv DATABASE_URL)"
  echo "LIVEKIT_URL=$(getv LIVEKIT_URL)"
  echo "LIVEKIT_API_KEY=$(getv LIVEKIT_API_KEY)"
  echo "LIVEKIT_API_SECRET=$(getv LIVEKIT_API_SECRET)"
} > .env.local
npm install --no-audit --no-fund --silent   # quick when nothing changed; picks up new packages

echo "== 6/6 Starting agent and web app =="
# An agent left over from an earlier run would keep answering calls with old code.
pkill -f "agent.py dev" 2>/dev/null || true
sleep 1
cd "$ROOT/agent"
python agent.py dev > "$ROOT/agent.log" 2>&1 &
AGENT_PID=$!
trap 'kill $AGENT_PID 2>/dev/null' EXIT
cd "$ROOT/web"
case " $* " in
  *" --dev "*)
    echo "Agent running (log: agent.log). Open http://localhost:3000  -  Ctrl+C stops everything."
    npm run dev ;;
  *)
    # The built version is faster and never reloads the page in the middle of a call.
    echo "Building the web app (about half a minute)..."
    npm run build > "$ROOT/web-build.log" 2>&1 || { echo "Web build failed. See web-build.log"; tail -20 "$ROOT/web-build.log"; exit 1; }
    echo "Agent running (log: agent.log). Open http://localhost:3000  -  Ctrl+C stops everything."
    npm run start ;;
esac
