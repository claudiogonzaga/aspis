#!/usr/bin/env bash
# Gera o instalador único Clipeo-<versão>.dmg a partir do .app empacotado.
#
# Uso:
#   ./make_dmg.sh            # builda o .app (py2app), assina e empacota o .dmg
#   ./make_dmg.sh --no-build # só assina + empacota um dist/Clipeo.app já existente
#
# O .dmg contém o Clipeo.app e um atalho para /Applications (instalar arrastando).
# NOTA: bundle/executável é ASCII ("Clipeo") — nome com acento quebra o codesign.
# O nome de exibição "Clipeo" vem do CFBundleDisplayName. O volume do .dmg usa o
# nome bonito.
set -euo pipefail

BUNDLE="Clipeo"          # nome do .app/executável (ASCII, p/ codesign)
VOL="Clipeo"             # nome de exibição do volume do .dmg
VERSION="0.1.0"
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/.venv/bin/python"
DIST="$HERE/dist"
APP="$DIST/$BUNDLE.app"
DMG="$DIST/$BUNDLE-$VERSION.dmg"

if [[ "${1:-}" != "--no-build" ]]; then
  echo "==> Buildando $BUNDLE.app via py2app"
  rm -rf "$HERE/build" "$DIST"
  "$PY" "$HERE/setup.py" py2app
fi

[[ -d "$APP" ]] || { echo "ERRO: $APP não encontrado. Rode sem --no-build."; exit 1; }

echo "==> Assinando (ad-hoc) o bundle"
"$HERE/assets/sign_app.sh" "$APP"

echo "==> Empacotando $DMG"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "$VOL" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

echo "==> Pronto: $DMG"
hdiutil verify "$DMG" >/dev/null && echo "    checksum VÁLIDO"
