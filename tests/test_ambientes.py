"""Detecção de ambientes sem zonas: paredes duplas, porta com bloco, divisa por projeção e proposta."""

import ezdxf
import pytest

from quantum.dxf_acabamentos import gerar_dxf_acabamentos
from quantum.orquestrador import analisar

from test_acabamentos import _etiqueta


def _retangulo(msp, x0, y0, x1, y1, camada):
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": camada})


def _quadro(msp):
    for tipo, x0 in (("PISO", 100), ("PAREDE", 120), ("TETO", 140)):
        msp.add_mtext(f"ESPECIFICAÇÃO - {tipo}", dxfattribs={"layer": "TEXTO", "insert": (x0 + 5.15, 50)})
        msp.add_mtext("01", dxfattribs={"layer": "TEXTO", "insert": (x0, 49.55)})
        msp.add_mtext(f"{tipo} UM", dxfattribs={"layer": "TEXTO", "insert": (x0 + 0.47, 49.55)})


def _rotulo(doc, msp, nome, area, x, y):
    msp.add_mtext(f"{nome}\\P{area:.2f} m2".replace(".", ","), dxfattribs={"layer": "TEXTO", "insert": (x, y)})
    _etiqueta(doc, msp, x - 0.28, y + 0.07, "01", "01", "01", nome=f"Rótulo_{nome.replace(' ', '_')}")


def _paredes(msp, x0, y0, x1, y1, e=0.15):
    """Parede de espessura e em volta de um retângulo interno (duas linhas, como no CAD)."""
    _retangulo(msp, x0, y0, x1, y1, "ALVENARIA")
    _retangulo(msp, x0 - e, y0 - e, x1 + e, y1 + e, "ALVENARIA")


def criar_planta(caminho):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    _quadro(msp)
    # QUARTO 3 x 4 com porta de 0,80 m na parede de baixo (bloco de esquadria com arco de abertura)
    msp.add_line((0, 0), (1.0, 0), dxfattribs={"layer": "ALVENARIA"})
    msp.add_line((1.8, 0), (3, 0), dxfattribs={"layer": "ALVENARIA"})
    for x0, y0, x1, y1 in ((3, 0, 3, 4), (3, 4, 0, 4), (0, 4, 0, 0)):
        msp.add_line((x0, y0), (x1, y1), dxfattribs={"layer": "ALVENARIA"})
    msp.add_line((-0.15, -0.15), (1.0, -0.15), dxfattribs={"layer": "ALVENARIA"})
    msp.add_line((1.8, -0.15), (3.15, -0.15), dxfattribs={"layer": "ALVENARIA"})
    for a, b in (((3.15, -0.15), (3.15, 4.15)), ((3.15, 4.15), (-0.15, 4.15)), ((-0.15, 4.15), (-0.15, -0.15))):
        msp.add_line(a, b, dxfattribs={"layer": "ALVENARIA"})
    porta = doc.blocks.new(name="PORTA_80")
    porta.add_line((0, 0), (0, -0.15), dxfattribs={"layer": "ALVENARIA"})  # batentes dentro da parede
    porta.add_line((0.8, 0), (0.8, -0.15), dxfattribs={"layer": "ALVENARIA"})
    porta.add_line((0, -0.15), (0, -0.95), dxfattribs={"layer": "ESQ"})  # folha aberta, para fora
    porta.add_arc((0, -0.15), 0.8, 270, 0, dxfattribs={"layer": "ESQ"})
    msp.add_blockref("PORTA_80", (1.0, 0), dxfattribs={"layer": "ESQ"})
    _rotulo(doc, msp, "QUARTO", 12.0, 1.0, 2.0)

    # COZINHA 2 x 3 + SERVIÇO 1 x 3 integrados, separados por linha de projeção
    _paredes(msp, 10, 0, 13, 3)
    msp.add_line((12, 0), (12, 3), dxfattribs={"layer": "PROJ"})
    _rotulo(doc, msp, "COZINHA", 6.0, 10.8, 1.5)
    _rotulo(doc, msp, "SERVICO", 3.0, 12.3, 1.5)

    # VARANDA A 4 x 2 + VARANDA B 2 x 2 sem nada no meio: divisa proposta
    _paredes(msp, 20, 0, 26, 2)
    _rotulo(doc, msp, "VARANDA A", 8.0, 21.5, 1.0)
    _rotulo(doc, msp, "VARANDA B", 4.0, 25.0, 1.0)

    # Área do rótulo não confere com o espaço (4 x 4 = 16, rótulo diz 10): não aceita
    _paredes(msp, 30, 0, 34, 4)
    _rotulo(doc, msp, "DEPOSITO", 10.0, 31.5, 2.0)
    doc.saveas(caminho)


def _amb(rel):
    return {a["nome"]: a for a in rel.acabamentos["ambientes"]}


def test_detecta_ambientes_pela_geometria(tmp_path):
    arq = tmp_path / "planta.dxf"
    criar_planta(arq)
    rel = analisar(arq, parametros={"altura_parede_01": 1.0})
    a = _amb(rel)
    # quarto: porta fechada pelo bloco, a folha aberta não invade nem vaza
    assert a["QUARTO"]["contorno_origem"] == "paredes"
    assert a["QUARTO"]["area_contorno_m2"] == pytest.approx(12.0, rel=0.01)
    assert a["QUARTO"]["perimetro_m"] == pytest.approx(14.0, rel=0.02)
    # integrados com projeção: divisa pela linha, que não conta como parede
    assert a["COZINHA"]["contorno_origem"] == "divisao"
    assert a["COZINHA"]["area_contorno_m2"] == pytest.approx(6.0, rel=0.01)
    assert a["COZINHA"]["perimetro_m"] == pytest.approx(7.0, rel=0.02)
    assert a["SERVICO"]["area_contorno_m2"] == pytest.approx(3.0, rel=0.01)
    # sem linha: divisa proposta proporcional às áreas
    assert a["VARANDA A"]["contorno_origem"] == "proposta"
    assert a["VARANDA A"]["area_contorno_m2"] == pytest.approx(8.0, rel=0.01)
    assert a["VARANDA B"]["area_contorno_m2"] == pytest.approx(4.0, rel=0.01)
    assert a["VARANDA B"]["perimetro_m"] == pytest.approx(6.0, rel=0.02)
    # divergência de área: nada aceito, vira pendência
    assert a["DEPOSITO"]["contorno"] is None
    msgs = " ".join(p.mensagem for p in rel.pendencias)
    assert "Divisa proposta" in msgs and "VARANDA A" in msgs
    assert "sem contorno reconhecido" in msgs and "DEPOSITO" in msgs


def test_dxf_gerado_separa_divisa_proposta(tmp_path):
    arq = tmp_path / "planta.dxf"
    criar_planta(arq)
    rel = analisar(arq)
    saida = tmp_path / "planta_acabamentos.dxf"
    gerar_dxf_acabamentos(arq, rel.acabamentos, saida)
    msp = ezdxf.readfile(saida).modelspace()
    assert len(msp.query('LWPOLYLINE[layer=="QTD-PISO-01-PROPOSTA"]')) == 2
    assert len(msp.query('LWPOLYLINE[layer=="QTD-PISO-01"]')) == 3  # quarto, cozinha, serviço


def test_muitos_pedacos_de_projecao_nao_viram_divisa_proposta(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    _quadro(msp)
    _paredes(msp, 0, 0, 10, 2)
    for x in range(1, 10):  # 6 pedaços para SALA (12 m²) e 4 para VARANDA (8 m²)
        msp.add_line((x, 0), (x, 2), dxfattribs={"layer": "PROJ"})
    _rotulo(doc, msp, "SALA", 12.0, 3.0, 1.0)
    _rotulo(doc, msp, "VARANDA", 8.0, 8.0, 1.0)
    arq = tmp_path / "pedacos.dxf"
    doc.saveas(arq)
    a = _amb(analisar(arq))
    assert a["SALA"]["contorno_origem"] == "divisao"
    assert a["SALA"]["area_contorno_m2"] == pytest.approx(12.0, rel=0.01)
    assert a["VARANDA"]["area_contorno_m2"] == pytest.approx(8.0, rel=0.01)
