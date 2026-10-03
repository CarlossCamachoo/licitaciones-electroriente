#!/bin/bash
# Arranca el panel del radar (si hace falta) y lo abre en una ventana propia.
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
PUERTO=8765
URL="http://127.0.0.1:$PUERTO/"
if ! nc -z 127.0.0.1 $PUERTO 2>/dev/null; then
  nohup "$RAIZ/.venv/bin/python" "$RAIZ/src/servidor.py" --puerto $PUERTO >> /tmp/radar-panel.log 2>&1 &
  for i in $(seq 1 30); do nc -z 127.0.0.1 $PUERTO 2>/dev/null && break; sleep 0.5; done
fi
if [ -d "/Applications/Google Chrome.app" ]; then
  open -na "Google Chrome" --args --app="$URL"
else
  open "$URL"
fi
