#!/usr/bin/env bash
# Baixa o Pyodide 0.27.2 (só o núcleo e os pacotes que o motor usa) para web/public/pyodide.
# Serve para verificar o site num ambiente sem acesso ao CDN jsDelivr; gere o site com
#   VITE_PYODIDE_URL=./pyodide/ npm run build
# O site publicado continua usando o CDN.
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=web/public/pyodide
VERSAO=0.27.2
if [ -f "$DEST/pyodide.mjs" ]; then echo "Pyodide já está em $DEST"; exit 0; fi
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fsSL -o "$TMP/pyodide.tar.bz2" "https://github.com/pyodide/pyodide/releases/download/$VERSAO/pyodide-$VERSAO.tar.bz2"
tar -xjf "$TMP/pyodide.tar.bz2" -C "$TMP" --wildcards \
  'pyodide/pyodide.mjs' 'pyodide/pyodide.js' 'pyodide/pyodide.asm.*' 'pyodide/python_stdlib.zip' \
  'pyodide/pyodide-lock.json' 'pyodide/package.json' \
  'pyodide/numpy-*.whl' 'pyodide/PyYAML-*.whl' 'pyodide/fonttools-*.whl' 'pyodide/pyparsing-*.whl' \
  'pyodide/typing_extensions-*.whl' 'pyodide/shapely-*.whl'
mkdir -p web/public
mv "$TMP/pyodide" "$DEST"
du -sh "$DEST"
