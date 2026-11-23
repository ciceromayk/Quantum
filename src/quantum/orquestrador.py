"""Orquestrador: coordena o grupo de agentes.

Fluxo:  Ingestão → Agentes de disciplina (layout, estrutural, elétrica, hidráulica, acabamentos)
        → Auditor → Orçamentista (opcional) → Relatório
"""

from __future__ import annotations

from pathlib import Path

from .agentes import AgenteAcabamentos, AgenteAuditor, AgenteDisciplina, AgenteOrcamentista
from .ingestao import carregar
from .modelos import Relatorio
from .regras import carregar_regras


def analisar(
    arquivo: str | Path,
    *,
    regras: str | Path | None = None,
    unidade: str | None = None,
    parametros: dict[str, float | str] | None = None,
    tabela_precos: str | Path | None = None,
    bdi: float | None = None,
    disciplinas: list[str] | None = None,
) -> Relatorio:
    parametros = parametros or {}
    r = carregar_regras(regras)
    desenho = carregar(arquivo, unidade=unidade)
    rel = Relatorio(desenho=desenho, parametros=parametros, bdi=bdi)

    usadas: set[str] = set()
    medidas: dict = {}
    rotuladas: set[str] = set()
    for regra_disc in r.disciplinas:
        if disciplinas and regra_disc.chave not in disciplinas:
            continue
        res = AgenteDisciplina(regra_disc, parametros).executar(desenho)
        rel.itens += res.itens
        rel.pendencias += res.pendencias
        usadas |= res.camadas_usadas
        medidas.update(res.handles_medidos)
        rotuladas |= {i.codigo for i in regra_disc.itens if i.rotular_por_texto}

    if not disciplinas or "acabamentos" in disciplinas:
        itens_ac, pend_ac, resumo_ac = AgenteAcabamentos(r.acabamentos, parametros).executar(desenho)
        rel.itens += itens_ac
        rel.pendencias += pend_ac
        rel.acabamentos = resumo_ac

    pend, nao_class = AgenteAuditor(r).auditar(desenho, usadas, medidas, rotuladas)
    rel.pendencias = pend + rel.pendencias
    rel.camadas_nao_classificadas = nao_class

    if tabela_precos:
        orc, pend_orc = AgenteOrcamentista(tabela_precos).orcar(rel.itens)
        rel.orcamento = orc
        rel.pendencias += pend_orc
    return rel
