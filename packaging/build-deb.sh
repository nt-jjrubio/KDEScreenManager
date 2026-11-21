#!/bin/sh
# Construye build/kdescreenmanager_<versión>_all.deb a partir de package/.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
ID=org.kdescreenmanager.applet
BUILD="$ROOT/build"
STAGE="$BUILD/staging"

VERSION=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["KPlugin"]["Version"])' "$ROOT/package/metadata.json")

# Con cambios sin confirmar se añade el hash de git para no confundir builds de prueba.
if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    if [ -n "$(git -C "$ROOT" status --porcelain)" ]; then
        VERSION="$VERSION+git$(git -C "$ROOT" rev-parse --short HEAD)"
    fi
fi

NAME=$(git -C "$ROOT" config user.name 2>/dev/null || true)
EMAIL=$(git -C "$ROOT" config user.email 2>/dev/null || true)
MAINTAINER="${DEB_MAINTAINER:-${NAME:-KDEScreenManager} <${EMAIL:-root@localhost}>}"

rm -rf "$STAGE"
DEST="$STAGE/usr/share/plasma/plasmoids/$ID"
mkdir -p "$DEST" "$STAGE/DEBIAN" "$STAGE/usr/share/doc/kdescreenmanager"
cp -r "$ROOT/package/." "$DEST/"
find "$DEST" -name '__pycache__' -prune -exec rm -rf {} +
find "$STAGE" -type d -exec chmod 755 {} +
find "$DEST" -type f -exec chmod 644 {} +
chmod 755 "$DEST/contents/code/kdescreenmanager-helper.py"
cp "$ROOT/CHANGELOG.md" "$STAGE/usr/share/doc/kdescreenmanager/"
[ -f "$ROOT/README.md" ] && cp "$ROOT/README.md" "$STAGE/usr/share/doc/kdescreenmanager/"
cp "$ROOT/packaging/copyright" "$STAGE/usr/share/doc/kdescreenmanager/copyright"
chmod 644 "$STAGE"/usr/share/doc/kdescreenmanager/*

SIZE=$(du -sk "$STAGE/usr" | cut -f1)
sed -e "s|@VERSION@|$VERSION|" -e "s|@MAINTAINER@|$MAINTAINER|" -e "s|@SIZE@|$SIZE|" \
    "$ROOT/packaging/control.in" > "$STAGE/DEBIAN/control"
install -m 755 "$ROOT/packaging/postinst" "$STAGE/DEBIAN/postinst"

OUT="$BUILD/kdescreenmanager_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT" >/dev/null
echo "$OUT"
