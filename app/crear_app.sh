#!/bin/bash
# Crea "Radar de Licitaciones.app" en ~/Applications.
# Al abrirla, arranca el panel (app/lanzar.sh) y lo abre en su propia ventana.
# Uso:  bash app/crear_app.sh
set -e
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
APP="$HOME/Applications/Radar de Licitaciones.app"

rm -rf "$APP"
mkdir -p "$HOME/Applications"

# Lanzador: arranca el panel si no esta corriendo y lo abre en su propia ventana.
LANZADOR="$RAIZ/app/lanzar.sh"
osacompile -o "$APP" -e "do shell script \"/bin/bash '$LANZADOR' >/dev/null 2>&1 &\""

# Iconos y modo sin icono extra en el Dock mientras arranca.
cp "$RAIZ/app/Radar.icns" "$APP/Contents/Resources/applet.icns"
/usr/libexec/PlistBuddy -c "Set :CFBundleName 'Radar de Licitaciones'" "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$APP/Contents/Info.plist" 2>/dev/null || true
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
touch "$APP"
echo "Listo: $APP"
