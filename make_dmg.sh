#!/usr/bin/env bash
# Gera o instalador único Clípeo-<versão>.dmg a partir do .app empacotado.
#
# Uso:
#   ./make_dmg.sh            # builda o .app (py2app) e empacota o .dmg
#   ./make_dmg.sh --no-build # só empacota o .dmg de um dist/Clípeo.app já existente
#
# O .dmg resultante contém o Clípeo.app e um atalho para /Applications,
# permitindo instalar arrastando o app para a pasta Aplicativos.
set -euo pipefail

APP_NAME="Clípeo"
VERSION="0.1.0"
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/.venv/bin/python"
DIST="$HERE/dist"
APP="$DIST/$APP_NAME.app"
DMG="$DIST/$APP_NAME-$VERSION.dmg"

if [[ "${1:-}" != "--no-build" ]]; then
  echo "==> Buildando $APP_NAME.app via py2app"
  rm -rf "$HERE/build" "$DIST"
  "$PY" "$HERE/setup.py" py2app
fi

[[ -d "$APP" ]] || { echo "ERRO: $APP não encontrado. Rode sem --no-build."; exit 1; }

echo "==> Empacotando $DMG"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

echo "==> Pronto: $DMG"
hdiutil verify "$DMG" >/dev/null && echo "    checksum VÁLIDO"
