"""Gera um DXF NOVO com polilinhas fechadas por acabamento. O arquivo original não é alterado.

Para cada ambiente com contorno e etiqueta, cria uma LWPOLYLINE fechada em cada camada
QTD-PISO-<código>, QTD-PAREDE-<código> e QTD-TETO-<código>. A descrição do quadro de
acabamentos vai na descrição da camada.
"""

from __future__ import annotations

from pathlib import Path

from .ingestao import abrir_documento

CORES = {"piso": 3, "parede": 1, "teto": 5}  # verde, vermelho, azul (ACI)


def gerar_dxf_acabamentos(origem: str | Path, acabamentos: dict, saida: str | Path) -> int:
    """Devolve o número de polilinhas criadas. Não grava nada se nenhum ambiente tem contorno."""
    ambientes = [a for a in acabamentos.get("ambientes", []) if a.get("contorno") and a.get("codigos")]
    if not ambientes:
        return 0
    if Path(origem).resolve() == Path(saida).resolve():
        raise ValueError("O DXF gerado precisa ter outro nome: o original não é alterado.")
    doc = abrir_documento(origem)
    msp = doc.modelspace()
    catalogo = acabamentos.get("catalogo", {})
    n = 0
    for a in ambientes:
        for tipo, cod in sorted(a["codigos"].items()):
            if tipo not in CORES:
                continue
            nome = f"QTD-{tipo.upper()}-{cod}"
            if nome not in doc.layers:
                camada = doc.layers.add(nome, color=CORES[tipo])
                camada.description = catalogo.get(tipo, {}).get(cod, "")[:200]
            pts = [tuple(p) for p in a["contorno"]]
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts = pts[:-1]
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": nome})
            n += 1
    doc.saveas(saida)
    return n
