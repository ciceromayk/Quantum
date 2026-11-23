"""Leitura de alturas de revestimento de parede a partir de cortes/vistas em DXF.

Em corte, o revestimento aparece como hachura de padrão próprio (ex.: GRELHA_60X60 para
porcelanato 60×60) na parede vista ao fundo. Para cada pilha de hachuras de revestimento
(mesma faixa horizontal, interrompida por bancadas ou faixas):

- base = parte de baixo da pilha (piso acabado);
- topo = parte de cima da pilha, cortada pela primeira laje/forro (hachura de concreto)
  que a cobre;
- ambiente = texto de nome dentro da faixa da pilha.

AVISO: alturas de corte valem só para os ambientes cortados e precisam de conferência.
Não presume nada para ambientes que não aparecem no corte.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ezdxf import bbox

from .ingestao import abrir_documento, limpar_texto

PADRAO_REVESTIMENTO = r"GRELHA|CER[AÂ]MIC|AZULEJ|PORCELAN|PASTILH|REVEST"
PADRAO_LAJE = r"CONCRETO"
RX_NAO_NOME = re.compile(r"^[\d\s.,+\-()°ºPO]+$|\(P\.O\.\)|TIPO$|^\d")


@dataclass
class AlturaCorte:
    ambiente: str
    padrao: str
    altura_m: float
    base_y: float
    x_min: float
    x_max: float
    interrupcoes: list[tuple[float, float]] = field(default_factory=list)  # (de_m, ate_m) sem revestimento


def _caixa(e):
    b = bbox.extents([e])
    return (b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y) if b.has_data else None


def ler_alturas_corte(
    caminho: str | Path,
    padrao_revestimento: str = PADRAO_REVESTIMENTO,
    padrao_laje: str = PADRAO_LAJE,
    fator_m: float | None = None,
) -> list[AlturaCorte]:
    doc = abrir_documento(caminho)
    msp = doc.modelspace()
    if fator_m is None:
        fator_m = {4: 0.001, 5: 0.01, 6: 1.0, 14: 0.1}.get(int(doc.header.get("$INSUNITS", 0)))
    if not fator_m:
        raise ValueError("Unidade do corte desconhecida ($INSUNITS). Informe a unidade.")
    rx_rev = re.compile(padrao_revestimento, re.IGNORECASE)
    rx_laje = re.compile(padrao_laje, re.IGNORECASE)
    tol = 0.02 / fator_m

    rev, lajes, textos = [], [], []
    for e in msp:
        t = e.dxftype()
        if t == "HATCH":
            nome = e.dxf.pattern_name or ""
            if rx_rev.search(nome) or rx_laje.search(nome):
                c = _caixa(e)
                if c and c[2] - c[0] > tol and c[3] - c[1] > tol:
                    (rev if rx_rev.search(nome) else lajes).append((nome, c))
        elif t in ("TEXT", "MTEXT"):
            txt = limpar_texto(e.plain_text() if t == "MTEXT" else e.dxf.text)
            if txt and not RX_NAO_NOME.search(txt):
                textos.append((txt, e.dxf.insert.x, e.dxf.insert.y))

    # Agrupa hachuras de revestimento em colunas (mesma faixa em x) e empilha em y.
    pilhas: list[list[tuple[str, tuple]]] = []
    for item in sorted(rev, key=lambda r: (round(r[1][0] / tol), r[1][1])):
        _, c = item
        for p in pilhas:
            pc = p[-1][1]
            mesma_coluna = c[0] < max(q[1][2] for q in p) - tol and c[2] > min(q[1][0] for q in p) + tol
            separado_por_laje = any(
                lc[0] < c[2] - tol and lc[2] > c[0] + tol and lc[1] < c[1] + tol and lc[3] > pc[3] - tol
                for _, lc in lajes
            )
            if mesma_coluna and 0 <= c[1] - pc[3] <= 0.25 / fator_m and not separado_por_laje:
                p.append(item)
                break
        else:
            pilhas.append([item])

    out: list[AlturaCorte] = []
    for p in pilhas:
        x0 = min(q[1][0] for q in p)
        x1 = max(q[1][2] for q in p)
        base = min(q[1][1] for q in p)
        topo = max(q[1][3] for q in p)
        # laje/forro em corte que cobre a faixa: o revestimento visível termina embaixo dela
        cobre = [c[1] for _, c in lajes if c[0] < x1 - tol and c[2] > x0 + tol and base + tol < c[1] < topo - tol]
        if cobre:
            topo = min(cobre)
        nomes = [t for t in textos if x0 - 0.3 / fator_m <= t[1] <= x1 + 0.3 / fator_m and base <= t[2] <= topo]
        if not nomes:
            continue
        nomes.sort(key=lambda t: abs(t[1] - (x0 + x1) / 2))
        faixas = sorted((q[1][1], min(q[1][3], topo)) for q in p if q[1][1] < topo)
        vaos = [((a[1] - base) * fator_m, (b[0] - base) * fator_m) for a, b in zip(faixas, faixas[1:]) if b[0] - a[1] > tol]
        out.append(AlturaCorte(
            ambiente=nomes[0][0],
            padrao=p[0][0],
            altura_m=round((topo - base) * fator_m, 3),
            base_y=base,
            x_min=x0,
            x_max=x1,
            interrupcoes=[(round(a, 3), round(b, 3)) for a, b in vaos],
        ))
    return out
