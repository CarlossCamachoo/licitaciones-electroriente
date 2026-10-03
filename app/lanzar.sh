#!/bin/bash
# Arranca el panel del radar (si hace falta) y lo abre en una ventana propia.
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
PUERTO=8765
URL="http://127.0.0.1:$PUERTO/"
MARCA=/tmp/radar-panel.inicio
# Si el codigo o la configuracion cambiaron despues de encender el panel, se reinicia solo.
PID=$(lsof -ti tcp:$PUERTO -sTCP:LISTEN 2>/dev/null | head -1)
if [ -n "$PID" ]; then
  if [ ! -f "$MARCA" ] || [ -n "$(find "$RAIZ/src" "$RAIZ/config" \( -name '*.py' -o -name '*.yaml' \) -newer "$MARCA" 2>/dev/null | head -1)" ]; then
    kill "$PID" 2>/dev/null
    for i in $(seq 1 20); do nc -z 127.0.0.1 $PUERTO 2>/dev/null || break; sleep 0.25; done
  fi
fi
if ! nc -z 127.0.0.1 $PUERTO 2>/dev/null; then
  touch "$MARCA"
  nohup "$RAIZ/.venv/bin/python" "$RAIZ/src/servidor.py" --puerto $PUERTO >> /tmp/radar-panel.log 2>&1 &
  for i in $(seq 1 30); do nc -z 127.0.0.1 $PUERTO 2>/dev/null && break; sleep 0.5; done
fi
if [ -d "/Applications/Google Chrome.app" ]; then
  open -na "Google Chrome" --args --app="$URL"
else
  open "$URL"
fi
