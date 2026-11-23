"""Ponto de entrada usado no navegador (Pyodide), sem servidor.

O JavaScript grava o DXF no sistema de arquivos virtual do Pyodide e chama
`processar_dxf`. O retorno traz o resultado em JSON e os relatórios prontos
(Markdown e Excel em base64) para download direto no navegador.
"""

from __future__ import annotations

import base64
import io
import json
import os
import tempfile

from .orquestrador import analisar
from .relatorio import para_json, para_markdown, para_xlsx


def processar_dxf(caminho: str, parametros_json: str = "{}", unidade: str | None = None, cortes_json: str = "[]") -> str:
    parametros = {
        k: (v.strip().lower() if isinstance(v, str) else float(v))
        for k, v in json.loads(parametros_json or "{}").items()
        if v is not None and v != ""
    }
    cortes = json.loads(cortes_json or "[]")
    rel = analisar(caminho, unidade=unidade or None, parametros=parametros, cortes=cortes)
    buf = io.BytesIO()
    para_xlsx(rel, buf)
    dxf_b64 = None
    if rel.acabamentos:
        from .dxf_acabamentos import gerar_dxf_acabamentos

        # a entrada pode estar num sistema de arquivos só de leitura (WORKERFS): grava no temporário
        destino = os.path.join(tempfile.gettempdir(), os.path.basename(caminho) + ".acabamentos.dxf")
        if gerar_dxf_acabamentos(caminho, rel.acabamentos, destino):
            with open(destino, "rb") as fh:
                dxf_b64 = base64.b64encode(fh.read()).decode("ascii")
            os.remove(destino)
    return json.dumps(
        {
            "resultado": json.loads(para_json(rel)),
            "markdown": para_markdown(rel),
            "xlsx_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
            "dxf_acabamentos_base64": dxf_b64,
        },
        ensure_ascii=False,
    )
