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
        k: (v if k.startswith("_") and isinstance(v, str) else v.strip().lower() if isinstance(v, str) else float(v))
        for k, v in json.loads(parametros_json or "{}").items()
        if v is not None and v != ""
    }
    cortes = json.loads(cortes_json or "[]")
    rel = analisar(caminho, unidade=unidade or None, parametros=parametros, cortes=cortes)
    buf = io.BytesIO()
    para_xlsx(rel, buf)
    geo = None
    msp = getattr(rel.desenho, "modelspace", None)
    if msp is not None:
        from .visualizacao import geometria

        try:
            geo = geometria(msp, rel.desenho.fator_m or 1.0)
            geo["fator_m"] = rel.desenho.fator_m or 1.0
        except Exception as exc:  # o visualizador é extra: não derruba a análise
            geo = {"erro": str(exc)}
    dxf_b64 = None
    if rel.acabamentos:
        from .dxf_acabamentos import gerar_dxf_acabamentos

        # a entrada pode estar num sistema de arquivos só de leitura (WORKERFS): grava no temporário
        destino = os.path.join(tempfile.gettempdir(), os.path.basename(caminho) + ".acabamentos.dxf")
        if gerar_dxf_acabamentos(caminho, rel.acabamentos, destino):
            with open(destino, "rb") as fh:
                dxf_b64 = base64.b64encode(fh.read()).decode("ascii")
            os.remove(destino)
        if isinstance(geo, dict) and "erro" not in geo:
            from .visualizacao import juntar_geradas

            try:  # as polilinhas geradas aparecem no visualizador como camadas próprias
                juntar_geradas(geo, rel.acabamentos)
            except Exception as exc:
                geo["erro_geradas"] = str(exc)
    pf_b64, pf_resumo = None, None
    if not (rel.paineis or {}).get("linhas"):
        # planta de arquitetura (ainda não é planta falada): gera a planta falada pré-classificada
        from .planta_falada import gerar as gerar_planta_falada

        destino = os.path.join(tempfile.gettempdir(), os.path.basename(caminho) + ".planta_falada.dxf")
        try:
            paredes: list = []
            pf_resumo = gerar_planta_falada(caminho, destino, unidade=unidade or None, desenho=rel.desenho, paredes_out=paredes)
            if pf_resumo.get("paredes"):
                with open(destino, "rb") as fh:
                    pf_b64 = base64.b64encode(fh.read()).decode("ascii")
                if isinstance(geo, dict) and "erro" not in geo:
                    from .visualizacao import juntar_planta_falada

                    try:  # os eixos aparecem na aba Planta, uma camada por sistema
                        juntar_planta_falada(geo, paredes)
                    except Exception as exc:
                        geo["erro_falada"] = str(exc)
            else:
                pf_resumo = None
        except Exception as exc:  # extra: não derruba a análise
            pf_resumo = {"erro": str(exc)}
        finally:
            if os.path.exists(destino):
                os.remove(destino)
    return json.dumps(
        {
            "resultado": json.loads(para_json(rel)),
            "dxf_planta_falada_base64": pf_b64,
            "planta_falada": pf_resumo,
            "markdown": para_markdown(rel),
            "xlsx_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
            "dxf_acabamentos_base64": dxf_b64,
            "geometria": geo,
        },
        ensure_ascii=False,
    )
