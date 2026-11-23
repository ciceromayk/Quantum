"""Processamento de um DXF enviado: roda o núcleo Quantum e guarda o resultado.

Na v1 roda em segundo plano no próprio processo da API (BackgroundTasks). Quando o
volume pedir, esta mesma função passa a ser chamada por uma fila (ex.: RQ/Celery).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from quantum import analisar
from quantum.ingestao import ErroIngestao
from quantum.relatorio import para_json, para_markdown, para_xlsx

from .db import Analise, agora

log = logging.getLogger("quantum_api")


def caminhos_relatorio(analise: Analise) -> dict[str, Path]:
    base = Path(analise.arquivo_caminho).with_suffix("")
    return {"md": base.with_suffix(".md"), "xlsx": base.with_suffix(".xlsx")}


def processar(sessoes: sessionmaker, analise_id: int) -> None:
    with sessoes() as s:
        analise = s.get(Analise, analise_id)
        if analise is None:
            return
        analise.status = "processando"
        analise.erro = None
        s.commit()
        pav = analise.pavimento
        try:
            rel = analisar(
                analise.arquivo_caminho,
                unidade=pav.unidade,
                parametros={k: float(v) for k, v in (pav.parametros or {}).items()},
            )
            analise.resultado = json.loads(para_json(rel))
            rotas = caminhos_relatorio(analise)
            rotas["md"].write_text(para_markdown(rel), encoding="utf-8")
            para_xlsx(rel, rotas["xlsx"])
            analise.status = "concluida"
        except (ErroIngestao, ValueError) as exc:
            analise.status = "erro"
            analise.erro = str(exc)
        except Exception as exc:  # erro inesperado: registra e não derruba a API
            log.exception("Falha ao processar análise %s", analise_id)
            analise.status = "erro"
            analise.erro = f"Erro inesperado ao processar o arquivo: {type(exc).__name__}"
        analise.concluido_em = agora()
        s.commit()
