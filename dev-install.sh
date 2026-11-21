#!/bin/sh
# Instalación local del plasmoid para desarrollo (no usar junto con el .deb).
# Uso: ./dev-install.sh           instala o actualiza en ~/.local/share/plasma/plasmoids
#      ./dev-install.sh --remove  desinstala la copia local
set -eu
ID=org.kdescreenmanager.applet
DIR=$(cd "$(dirname "$0")" && pwd)

if [ "${1:-}" = "--remove" ]; then
    kpackagetool6 -t Plasma/Applet -r "$ID"
    exit 0
fi

if [ -d /usr/share/plasma/plasmoids/$ID ]; then
    echo "AVISO: el paquete .deb ya está instalado; la copia local lo tapará." >&2
fi

chmod +x "$DIR/package/contents/code/kdescreenmanager-helper.py"
if kpackagetool6 -t Plasma/Applet -s "$ID" >/dev/null 2>&1; then
    kpackagetool6 -t Plasma/Applet -u "$DIR/package"
else
    kpackagetool6 -t Plasma/Applet -i "$DIR/package"
fi
echo "Instalado. Pruébalo en ventana con: plasmawindowed $ID"
echo "O añádelo en Bandeja del sistema → Configurar → Elementos → KDEScreenManager (puede hacer falta: plasmashell --replace &)"
