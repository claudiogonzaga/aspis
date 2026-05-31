#!/usr/bin/env bash
# Assina (ad-hoc) um .app do py2app na ordem correta: de dentro pra fora.
# Necessário porque `codesign --deep` falha na estrutura do py2app
# (MacOS/python + MacOS/<app> + Python.framework), gerando o erro
# "a sealed resource is missing or invalid" — que o Gatekeeper, sob
# quarentena, mostra como "está danificado".
#
# Uso: ./assets/sign_app.sh "dist/Clípeo.app"
set -euo pipefail

APP="${1:?uso: sign_app.sh <caminho-do-.app>}"
[[ -d "$APP" ]] || { echo "ERRO: $APP não existe"; exit 1; }

S=(codesign --force --sign -)
# NÃO usar --options runtime (hardened runtime): ele força library validation,
# que exige Team ID igual entre o executável e as libs. Como a assinatura é
# ad-hoc (sem Team ID), isso quebraria o dlopen do Python.framework
# ("different Team IDs"). Ad-hoc puro carrega as libs sem esse problema.

echo "==> assinando libs aninhadas (.dylib/.so)"
find "$APP/Contents" \( -name "*.dylib" -o -name "*.so" \) -print0 \
  | while IFS= read -r -d '' f; do "${S[@]}" "$f" >/dev/null; done

echo "==> assinando Python.framework"
for v in "$APP"/Contents/Frameworks/Python.framework/Versions/[0-9]*; do
  [[ -d "$v" ]] && "${S[@]}" "$v" >/dev/null
done

echo "==> assinando executáveis em MacOS/"
[[ -f "$APP/Contents/MacOS/python" ]] && "${S[@]}" "$APP/Contents/MacOS/python" >/dev/null
# executável principal = o que casa com CFBundleExecutable
MAIN="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$APP/Contents/Info.plist")"
"${S[@]}" "$APP/Contents/MacOS/$MAIN" >/dev/null

echo "==> assinando o bundle"
"${S[@]}" "$APP" >/dev/null

echo "==> verificando selo"
codesign --verify --deep --strict --verbose=2 "$APP" 2>&1 | tail -2
