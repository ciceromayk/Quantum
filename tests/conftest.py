"""Gera DXFs sintéticos com valores conhecidos para os testes."""

from __future__ import annotations

import ezdxf
import pytest


def _bloco(doc, nome: str) -> None:
    b = doc.blocks.new(name=nome)
    b.add_circle((0, 0), radius=50)


def criar_planta(caminho, insunits: int = 4) -> None:
    """Planta em milímetros:

    - SALA 4 x 5 m (20 m²) com texto "SALA" e texto de área ERRADO "21,00 m²"
    - QUARTO 3 x 3 m (9 m²) com texto "QUARTO" e "9,00 m²"
    - 1 contorno aberto na camada de ambientes
    - Paredes: 2 linhas de 4 m + 1 de 5 m = 13 m (uma linha de 4 m duplicada → 17 m)
    - 2 pilares 20x40 cm (0,08 m² cada)
    - 3 tomadas (bloco TUG) + 1 duplicada no mesmo ponto, 2 luminárias
    - Eletroduto: polilinha de 6 m
    - Água fria: 3,5 m; esgoto: arco de raio 1 m e 90° (≈1,5708 m)
    - Camada "PAISAGISMO" sem regra (deve virar pendência)
    """
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = insunits
    msp = doc.modelspace()
    for nome in ("TUG", "LUM", "PORTA80"):
        _bloco(doc, nome)

    msp.add_lwpolyline([(0, 0), (4000, 0), (4000, 5000), (0, 5000)], close=True, dxfattribs={"layer": "ARQ-AMBIENTE"})
    msp.add_text("SALA", dxfattribs={"layer": "ARQ-TEXTO", "insert": (1000, 2500)})
    msp.add_text("21,00 m²", dxfattribs={"layer": "ARQ-TEXTO", "insert": (1000, 2000)})
    msp.add_lwpolyline([(4000, 0), (7000, 0), (7000, 3000), (4000, 3000)], close=True, dxfattribs={"layer": "ARQ-AMBIENTE"})
    msp.add_text("QUARTO", dxfattribs={"layer": "ARQ-TEXTO", "insert": (5000, 1500)})
    msp.add_text("9,00 m²", dxfattribs={"layer": "ARQ-TEXTO", "insert": (5000, 1000)})
    msp.add_lwpolyline([(8000, 0), (9000, 0), (9000, 1000), (8000, 1000), (8000, 0)], dxfattribs={"layer": "ARQ-AMBIENTE"})

    msp.add_line((0, 0), (4000, 0), dxfattribs={"layer": "ARQ-PAREDE"})
    msp.add_line((0, 0), (4000, 0), dxfattribs={"layer": "ARQ-PAREDE"})  # duplicada
    msp.add_line((0, 5000), (4000, 5000), dxfattribs={"layer": "ARQ-PAREDE"})
    msp.add_line((0, 0), (0, 5000), dxfattribs={"layer": "ARQ-PAREDE"})
    msp.add_blockref("PORTA80", (2000, 0), dxfattribs={"layer": "ARQ-PORTA"})

    for x in (0, 4000):
        msp.add_lwpolyline([(x, 0), (x + 200, 0), (x + 200, 400), (x, 400)], close=True, dxfattribs={"layer": "EST-PILAR"})

    for p in [(500, 100), (1500, 100), (2500, 100), (2500, 100)]:
        msp.add_blockref("TUG", p, dxfattribs={"layer": "ELE-TOMADA"})
    for p in [(2000, 2500), (5500, 1500)]:
        msp.add_blockref("LUM", p, dxfattribs={"layer": "ELE-ILUMINACAO"})
    msp.add_point((3000, 100), dxfattribs={"layer": "ELE-TOMADA"})  # símbolo sem bloco
    msp.add_lwpolyline([(0, 100), (6000, 100)], dxfattribs={"layer": "ELE-ELETRODUTO"})

    msp.add_line((0, 4000), (3500, 4000), dxfattribs={"layer": "HID-AF"})
    msp.add_arc((0, 0), radius=1000, start_angle=0, end_angle=90, dxfattribs={"layer": "HID-ESGOTO"})

    msp.add_line((100, 100), (900, 900), dxfattribs={"layer": "PAISAGISMO"})
    doc.saveas(caminho)


@pytest.fixture
def planta(tmp_path):
    p = tmp_path / "planta.dxf"
    criar_planta(p)
    return p


@pytest.fixture
def planta_sem_unidade(tmp_path):
    p = tmp_path / "sem_unidade.dxf"
    criar_planta(p, insunits=0)
    return p
