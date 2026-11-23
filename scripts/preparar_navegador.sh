#!/usr/bin/env bash
# Gera as wheels Python que o navegador (Pyodide) instala: o pacote Quantum e as
# dependências puras que não vêm na distribuição do Pyodide.
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=web/public/py
mkdir -p "$DEST"
find "$DEST" -name '*.whl' -delete
pip wheel . --no-deps -w "$DEST" -q
pip download --no-deps --only-binary=:all: --platform any --python-version 3.12 --implementation py \
  -d "$DEST" -q "ezdxf==1.4.5" "openpyxl==3.1.5" "et_xmlfile==2.0.0"
ls "$DEST" | sed 's/^/  /' > /dev/stderr
( cd "$DEST" && ls *.whl ) | python3 -c "import json,sys; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" > "$DEST/wheels.json"
