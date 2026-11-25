"""Planta de arquitetura sintética (metros) -> planta falada pré-classificada -> planilha."""

import ezdxf
import pytest

from quantum.orquestrador import analisar
from quantum.planta_falada import CAMADA_A_CLASSIFICAR, CAMADA_INFERIDO, detectar_paredes, gerar


def parede(msp, camada, x0, y0, x1, y1, faces):
    """Parede horizontal ou vertical: uma linha por face, nos afastamentos dados a partir do eixo."""
    for d in faces:
        if y0 == y1:
            msp.add_line((x0, y0 + d), (x1, y1 + d), dxfattribs={"layer": camada})
        else:
            msp.add_line((x0 + d, y0), (x1 + d, y1), dxfattribs={"layer": camada})


def criar_arquitetura(caminho):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    # drywall 70 com chapa 12,5 mm dos dois lados (linhas do perfil e das chapas), 4 m, entre BWC e QUARTO
    parede(msp, "DRY WALL", 0, 3, 4, 3, (-0.0475, -0.035, 0.035, 0.0475))
    # alvenaria de 14 cm (só o bloco), 4 m, entre QUARTO e o exterior (sem rótulo do outro lado)
    parede(msp, "ALVENARIA", 0, 6, 4, 6, (-0.07, 0.07))
    # alvenaria fora do padrão (25 cm): vai para a camada a classificar
    parede(msp, "ALVENARIA", 8, 0, 8, 4, (-0.125, 0.125))
    for txt, x, y in (("BWC\\P3,50 m2", 2, 1.5), ("QUARTO\\P11,00 m2", 2, 4.5)):
        msp.add_mtext(txt, dxfattribs={"insert": (x, y), "char_height": 0.15, "layer": "TEXTO"})
    doc.saveas(caminho)


def test_detecta_e_classifica(tmp_path):
    arq = tmp_path / "arq.dxf"
    criar_arquitetura(arq)
    paredes, info = detectar_paredes(arq)
    por = {}
    for p in paredes:
        por.setdefault(p.especificacao, []).append(p)
    dw = por["PERFIL 70MM + ST + RU"][0]
    assert dw.nucleo_m == pytest.approx(0.07)
    assert sum(p.comprimento_m for p in por["PERFIL 70MM + ST + RU"]) == pytest.approx(4.0, abs=0.15)
    assert any("chapas" in x for x in dw.inferido)
    t14 = por["ALVENARIA TIJOLO DE 14CM"]
    assert sum(p.comprimento_m for p in t14) == pytest.approx(4.0, abs=0.2)
    assert any("tijolo" in x for x in t14[0].inferido)
    assert None in por  # a de 25 cm não é classificada


def test_gera_dxf_e_vira_planilha(tmp_path):
    arq, saida = tmp_path / "arq.dxf", tmp_path / "falada.dxf"
    criar_arquitetura(arq)
    r = gerar(arq, saida)
    assert r["paredes"] >= 3
    doc = ezdxf.readfile(saida)
    camadas = {e.dxf.layer for e in doc.modelspace()}
    assert {"0_DRY_WALL_70MM_+ST+RU", "0_TIJOLO CERAMICO_14CM", CAMADA_A_CLASSIFICAR, CAMADA_INFERIDO} <= camadas
    assert {"ALVENARIA", "DRY WALL"} <= camadas  # a arquitetura original continua no arquivo
    rel = analisar(saida, parametros={"pe_esquerdo": 2.88, "contrapiso": 0.05, "espessura_laje": 0.20})
    esp = {l["especificacao"] for l in rel.paineis["linhas"]}
    assert {"PERFIL 70MM + ST + RU", "ALVENARIA TIJOLO DE 14CM"} <= esp
