"""Ponto de entrada usado no navegador (Pyodide), sem servidor.

O JavaScript grava o DXF no sistema de arquivos virtual do Pyodide e chama
`processar_dxf`. O retorno traz o resultado em JSON e os relatórios prontos
(Markdown e Excel em base64) para download direto no navegador.
"""

from __future__ import annotations

import base64
import io
import json

from .orquestrador import analisar
from .relatorio import para_json, para_markdown, para_xlsx


def processar_dxf(caminho: str, parametros_json: str = "{}", unidade: str | None = None) -> str:
    parametros = {k: float(v) for k, v in json.loads(parametros_json or "{}").items()}
    rel = analisar(caminho, unidade=unidade or None, parametros=parametros)
    buf = io.BytesIO()
    para_xlsx(rel, buf)
    return json.dumps(
        {
            "resultado": json.loads(para_json(rel)),
            "markdown": para_markdown(rel),
            "xlsx_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
        },
        ensure_ascii=False,
    )
