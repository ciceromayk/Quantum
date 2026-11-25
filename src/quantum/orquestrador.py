"""Orquestrador: coordena o grupo de agentes.

Fluxo:  Ingestão → Agentes de disciplina (layout, estrutural, elétrica, hidráulica, acabamentos)
        → Auditor → Orçamentista (opcional) → Relatório
"""

from __future__ import annotations

from pathlib import Path

from .agentes import AgenteAcabamentos, AgenteAuditor, AgenteDisciplina, AgenteOrcamentista
from .ingestao import carregar
from .modelos import Pendencia, Relatorio, Severidade
from .regras import carregar_regras


def _alturas_dos_cortes(cortes) -> tuple[dict[str, float], list]:
    """Altura por nome de ambiente. Se o mesmo ambiente aparece com alturas diferentes, não escolhe."""
    from .cortes import ler_alturas_corte
    from .modelos import Pendencia, Severidade

    vistos: dict[str, set[float]] = {}
    sem_nome: list[float] = []
    for c in cortes:
        for a in ler_alturas_corte(c):
            vistos.setdefault(a.ambiente, set()).add(a.altura_m)
        sem_nome += list(getattr(ler_alturas_corte, "sem_nome", []))
    alturas = {k: next(iter(v)) for k, v in vistos.items() if len(v) == 1}
    pend = [
        Pendencia("acabamentos", Severidade.ALERTA,
                  f"{k}: alturas diferentes nos cortes ({', '.join(f'{x:.2f}' for x in sorted(v))} m). Nenhuma foi usada.",
                  acao_sugerida="Informe a altura correta desse ambiente.")
        for k, v in vistos.items() if len(v) > 1
    ]
    if alturas:
        lidas = ", ".join(f"{k} ({v:.2f} m)".replace(f"{v:.2f}", f"{v:.2f}".replace(".", ",")) for k, v in sorted(alturas.items())[:12])
        pend.append(Pendencia(
            "acabamentos", Severidade.INFO,
            f"Alturas lidas no(s) corte(s) para {len(alturas)} ambiente(s): {lidas}.",
            acao_sugerida="Os ambientes com outro nome ficam sem altura: informe em Parâmetros ou use o mesmo nome no corte.",
        ))
    if sem_nome:
        faixas = ", ".join(f"{h:.2f}".replace(".", ",") + " m" for h in sorted({round(h, 2) for h in sem_nome})[:8])
        pend.append(Pendencia(
            "acabamentos", Severidade.ALERTA,
            f"{len(sem_nome)} trecho(s) de revestimento no corte sem nome de ambiente dentro da faixa "
            f"(alturas {faixas}). Nenhuma altura foi aproveitada deles.",
            acao_sugerida="Escreva o nome do ambiente dentro do trecho cortado, ou informe a altura em Parâmetros "
                          "(altura_parede_<código>).",
        ))
    return alturas, pend


def analisar(
    arquivo: str | Path,
    *,
    regras: str | Path | None = None,
    unidade: str | None = None,
    parametros: dict[str, float | str] | None = None,
    tabela_precos: str | Path | None = None,
    bdi: float | None = None,
    disciplinas: list[str] | None = None,
    cortes: list[str | Path] | None = None,
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
        alturas, pend_cortes = _alturas_dos_cortes(cortes or [])
        itens_ac, pend_ac, resumo_ac = AgenteAcabamentos(r.acabamentos, parametros, alturas).executar(desenho)
        if resumo_ac:
            pend_ac += pend_cortes
            resumo_ac["alturas_corte"] = alturas
        rel.itens += itens_ac
        rel.pendencias += pend_ac
        rel.acabamentos = resumo_ac

    pend, nao_class = AgenteAuditor(r).auditar(desenho, usadas, medidas, rotuladas)
    rel.pendencias = pend + rel.pendencias
    if getattr(desenho, "ignoradas_layout", 0):
        rel.pendencias.append(Pendencia(
            "auditoria", Severidade.INFO,
            f"Lido só o Model: {desenho.ignoradas_layout} entidade(s) das pranchas (layouts) foram ignoradas.",
        ))
    rel.camadas_nao_classificadas = nao_class

    if tabela_precos:
        orc, pend_orc = AgenteOrcamentista(tabela_precos).orcar(rel.itens)
        rel.orcamento = orc
        rel.pendencias += pend_orc
    return rel
