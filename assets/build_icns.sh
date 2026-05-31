#!/usr/bin/env bash
# Gera clipeo.icns (na raiz do projeto) a partir de assets/clipeo_icon_1024.png,
# criando o .iconset com todos os tamanhos via sips e empacotando com iconutil.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
MASTER="$HERE/clipeo_icon_1024.png"
SET="$HERE/clipeo.iconset"
ICNS="$ROOT/clipeo.icns"

[[ -f "$MASTER" ]] || { echo "ERRO: $MASTER não existe. Rode make_icon.py antes."; exit 1; }

rm -rf "$SET"; mkdir -p "$SET"
gen() { sips -z "$2" "$2" "$MASTER" --out "$SET/$1" >/dev/null; }

gen icon_16x16.png        16
gen icon_16x16@2x.png     32
gen icon_32x32.png        32
gen icon_32x32@2x.png     64
gen icon_128x128.png      128
gen icon_128x128@2x.png   256
gen icon_256x256.png      256
gen icon_256x256@2x.png   512
gen icon_512x512.png      512
cp "$MASTER" "$SET/icon_512x512@2x.png"   # 1024

iconutil -c icns "$SET" -o "$ICNS"
rm -rf "$SET"
echo "==> Pronto: $ICNS"
ls -lh "$ICNS"
