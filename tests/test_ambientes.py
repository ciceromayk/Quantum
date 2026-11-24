"""Detecção de ambientes sem zonas: paredes duplas, porta com bloco, divisa por projeção e proposta."""

import math

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


def test_dxf_une_integrados_com_o_mesmo_piso(tmp_path):
    """Integrados com o mesmo acabamento viram uma polilinha só, sem a divisa (nem a proposta)."""
    arq = tmp_path / "planta.dxf"
    criar_planta(arq)
    rel = analisar(arq)
    saida = tmp_path / "planta_acabamentos.dxf"
    gerar_dxf_acabamentos(arq, rel.acabamentos, saida)
    msp = ezdxf.readfile(saida).modelspace()
    # todos usam piso 01: quarto sozinho, cozinha+serviço juntos, varanda A+B juntas
    assert len(msp.query('LWPOLYLINE[layer ? "QTD-PISO-01-PROPOSTA.*"]')) == 0
    piso = msp.query('LWPOLYLINE[layer ? "QTD-PISO-01 .*"]')
    assert len(piso) == 3
    areas = sorted(round(abs(_area(p)), 2) for p in piso)
    assert areas == pytest.approx([9.0, 12.0, 12.0], abs=0.05)  # varandas 8+4, quarto 12, coz 6+3
    # a parede continua ambiente por ambiente, em trechos abertos colados à parede
    parede = msp.query('LWPOLYLINE[layer ? "QTD-PAREDE-.*"]')
    assert len(parede) == 5  # um trecho por ambiente, sem as divisas
    comprimento = sum(
        sum(math.dist(pts[i][:2], pts[i + 1][:2]) for i in range(len(pts) - 1))
        for pts in ([list(p.get_points("xy")) for p in parede])
    )
    assert comprimento == pytest.approx(42.0, abs=0.05)


def _area(pl):
    pts = list(pl.get_points("xy"))
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts))) / 2


def test_integrados_com_acabamentos_diferentes_mantem_a_divisa():
    from quantum.dxf_acabamentos import _unir_integrados

    vizinhos = [
        {"contorno": [(0, 0), (2, 0), (2, 3), (0, 3)], "codigos": {"piso": "01"}},
        {"contorno": [(2, 0), (4, 0), (4, 3), (2, 3)], "codigos": {"piso": "01"}},
        {"contorno": [(4, 0), (6, 0), (6, 3), (4, 3)], "codigos": {"piso": "02"}},
    ]
    unido = _unir_integrados(vizinhos, "piso", 0.01)
    assert len(unido["01"]) == 1  # os dois de piso 01 viraram um só
    assert len(unido["02"]) == 1
    from shapely.geometry import Polygon

    assert Polygon(unido["01"][0][0]).area == pytest.approx(12.0, abs=0.05)
    assert Polygon(unido["02"][0][0]).area == pytest.approx(6.0, abs=0.05)


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


def test_dxf_gerado_e_montado_do_zero_e_abre_limpo(tmp_path):
    """O DXF de acabamentos é um arquivo novo (AutoCAD 2013) com a cópia do Model: cotas entram
    explodidas, máscaras são recriadas e nada que o AutoCAD recuse vem do arquivo de origem."""
    from ezdxf import recover

    arq = tmp_path / "planta.dxf"
    criar_planta(arq)
    doc = ezdxf.readfile(arq)
    msp = doc.modelspace()
    doc.dimstyles.new("COTA")
    msp.add_linear_dim(base=(0, 6), p1=(0, 4.15), p2=(3.15, 4.15), dimstyle="COTA").render()
    msp.add_wipeout([(40, 0), (41, 0), (41, 1), (40, 1)])
    doc.appids.new("APP_ESTRANHO")
    msp.add_line((50, 0), (51, 0)).set_xdata("APP_ESTRANHO", [(1000, "lixo")])
    doc.layouts.new("PRANCHA").add_line((0, 0), (1, 1))
    doc.saveas(arq)

    rel = analisar(arq)
    rel.acabamentos["catalogo"]["piso"]["01"] = "PISO UM\nlinha dois\tcom tab"
    saida = tmp_path / "planta_acabamentos.dxf"
    assert gerar_dxf_acabamentos(arq, rel.acabamentos, saida) > 0

    novo, auditoria = recover.readfile(saida)
    assert novo.dxfversion == "AC1027"
    assert not auditoria.errors and not auditoria.fixes
    verif = novo.audit()
    assert not verif.errors and not verif.fixes
    nmsp = novo.modelspace()
    assert len(nmsp.query("DIMENSION")) == 0 and len(nmsp.query("MTEXT TEXT")) > 0  # cota explodida
    assert len(nmsp.query("WIPEOUT")) == 1
    assert "APP_ESTRANHO" not in novo.appids
    assert "PRANCHA" not in novo.layouts.names()
    camada = next(c for c in novo.layers if c.dxf.name.startswith("QTD-PISO-01 "))
    assert camada.dxf.name == "QTD-PISO-01 PISO UM linha dois com tab"
    assert camada.description == "PISO UM linha dois com tab"
    assert novo.header["$INSUNITS"] == 6


def test_retificar_tira_reentrancia_de_esquadria_e_mantem_canto():
    """A saliência rasa do vão (batente, requadro) sai; o canto reentrante do ambiente fica."""
    from shapely.geometry import Polygon

    from quantum.ambientes import _retificar

    # retângulo 4 x 3 com uma saliência de 0,80 x 0,12 (requadro de janela) na parede de baixo
    com_vao = Polygon([(0, 0), (1.6, 0), (1.6, -0.12), (2.4, -0.12), (2.4, 0), (4, 0), (4, 3), (0, 3)])
    reto = _retificar(com_vao, 0.15)
    assert reto.area == pytest.approx(12.0, abs=0.01)
    assert len(reto.exterior.coords) == 5  # voltou a ser um retângulo (4 cantos + fechamento)
    # o mesmo retângulo em L: o canto é fundo e continua lá
    em_l = Polygon([(0, 0), (4, 0), (4, 3), (2, 3), (2, 1.5), (0, 1.5)])
    assert _retificar(em_l, 0.15).area == pytest.approx(em_l.area, rel=0.001)


def test_polilinhas_de_parede_ficam_coladas_na_parede_e_com_espessura(tmp_path):
    arq = tmp_path / "planta.dxf"
    criar_planta(arq)
    rel = analisar(arq)
    saida = tmp_path / "planta_acabamentos.dxf"
    gerar_dxf_acabamentos(arq, rel.acabamentos, saida)
    msp = ezdxf.readfile(saida).modelspace()

    piso = msp.query('LWPOLYLINE[layer ? "QTD-PISO-01 .*"]')
    parede = msp.query('LWPOLYLINE[layer ? "QTD-PAREDE-01 .*"]')
    assert piso and parede
    assert all(p.closed for p in piso), "piso e teto medem área: polilinha fechada"
    assert all(not p.closed for p in parede), "parede segue só os trechos com parede: polilinha aberta"
    assert {round(p.dxf.const_width, 4) for p in list(piso) + list(parede)} == {0.025}

    # COZINHA e SERVIÇO são separadas por uma linha de projeção: essa divisa não é parede
    amb = {a["nome"]: a for a in rel.acabamentos["ambientes"]}
    cozinha = amb["COZINHA"]
    assert cozinha["perimetro_m"] == pytest.approx(7.0, rel=0.02)  # 2 + 3 + 2, sem a divisa de 3 m
    assert sum(len(t) for t in cozinha["trechos_parede"]) > 0


def test_porta_nao_entra_no_contorno(tmp_path):
    """A folha e o arco de abertura são desenho da porta, não parede: o contorno fecha o vão reto."""
    arq = tmp_path / "planta.dxf"
    criar_planta(arq)
    a = _amb(analisar(arq))["QUARTO"]
    pts = a["contorno"]
    # a folha abre para fora (y de -0,15 a -0,95): nenhum ponto do contorno passa da parede
    assert min(y for _, y in pts) >= -0.16, pts
    assert a["area_contorno_m2"] == pytest.approx(12.0, rel=0.02)


def test_canto_sai_limpo_mesmo_com_alisar(tmp_path):
    """Degraus rasos no canto (alisar de porta, requadro) viram um canto em esquadro."""
    from shapely.geometry import Polygon

    from quantum.ambientes import _retificar

    # retângulo 4 x 3 com um degrau de 4 cm no canto superior direito (alisar)
    com_degrau = Polygon([(0, 0), (4, 0), (4, 2.96), (3.96, 2.96), (3.96, 3), (0, 3)])
    reto = _retificar(com_degrau, 0.15)
    assert len(reto.exterior.coords) == 5
    assert reto.area == pytest.approx(12.0, abs=0.01)
    # chanfro de verdade (0,5 m) não é degrau e continua no contorno
    chanfro = Polygon([(0, 0), (4, 0), (4, 2.5), (3.5, 3), (0, 3)])
    assert len(_retificar(chanfro, 0.15).exterior.coords) == 6


def test_vao_sem_linha_de_parede_fecha_pelo_arco(tmp_path):
    """Bloco de porta sem linha de parede: o raio que atravessa o vão fecha, a folha não."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    _quadro(msp)
    # SALA 4 x 3 com um vão de 0,80 m na parede de baixo (face interna e externa abertas)
    for y in (0.0, -0.15):
        msp.add_line((-0.15 if y else 0, y), (1.0, y), dxfattribs={"layer": "ALVENARIA"})
        msp.add_line((1.8, y), (4.15 if y else 4, y), dxfattribs={"layer": "ALVENARIA"})
    for x0, y0, x1, y1 in ((4, 0, 4, 3), (4, 3, 0, 3), (0, 3, 0, 0)):
        msp.add_line((x0, y0), (x1, y1), dxfattribs={"layer": "ALVENARIA"})
    for a, b in (((4.15, -0.15), (4.15, 3.15)), ((4.15, 3.15), (-0.15, 3.15)), ((-0.15, 3.15), (-0.15, -0.15))):
        msp.add_line(a, b, dxfattribs={"layer": "ALVENARIA"})
    # bloco só com a porta: arco de abertura, sem nenhuma linha em camada de parede
    porta = doc.blocks.new(name="SO_PORTA")
    porta.add_arc((1.0, 0), 0.8, 270, 0, dxfattribs={"layer": "ESQ"})  # folha para fora
    msp.add_blockref("SO_PORTA", (0, 0), dxfattribs={"layer": "ESQ"})
    _rotulo(doc, msp, "SALA", 12.0, 2.0, 1.5)
    arq = tmp_path / "vao.dxf"
    doc.saveas(arq)

    a = _amb(analisar(arq))["SALA"]
    assert a["contorno_origem"] == "paredes"
    assert a["area_contorno_m2"] == pytest.approx(12.0, rel=0.02)
    assert min(y for _, y in a["contorno"]) >= -0.16  # a folha aberta não entra no contorno


def test_degrau_de_parede_fica_no_contorno_e_requadro_some():
    """Requadro de janela (mesmo plano) é aplainado; degrau de parede (ponta, viradinha) fica."""
    from quantum.ambientes import _retificar
    from shapely.geometry import Polygon

    requadro = Polygon([(0, 0), (5, 0), (5, 3), (3, 3), (3, 3.08), (2, 3.08), (2, 3), (0, 3)])
    reto = _retificar(requadro, 0.15)
    assert len(reto.exterior.coords) == 5  # virou retângulo
    assert reto.area == pytest.approx(15.0, abs=0.01)

    degrau = Polygon([(0, 0), (5, 0), (5, 3), (2, 3), (2, 3.11), (0, 3.11)])
    reto = _retificar(degrau, 0.15)
    pts = [(round(x, 3), round(y, 3)) for x, y in reto.exterior.coords]
    assert (2.0, 3.0) in pts and (2.0, 3.11) in pts  # a virada continua lá
    assert reto.area == pytest.approx(degrau.area, abs=0.001)


def test_geometria_recebe_as_polilinhas_geradas(tmp_path):
    """O visualizador mostra as mesmas polilinhas do DXF gerado, como camadas QTD-*."""
    import ezdxf as _ezdxf
    from quantum.visualizacao import geometria, juntar_geradas

    arq = tmp_path / "planta.dxf"
    criar_planta(arq)
    rel = analisar(arq)
    geo = geometria(_ezdxf.readfile(arq).modelspace(), rel.desenho.fator_m or 1.0)
    antes = set(geo["camadas"])
    juntar_geradas(geo, rel.acabamentos)
    assert geo["geradas"], "nenhuma camada gerada"
    assert all(n.startswith("QTD-") for n in geo["geradas"])
    assert set(geo["geradas"]) == set(geo["camadas"]) - antes
    assert geo["largura_gerada"] == 0.025
    # mesma contagem de polilinhas do arquivo gerado
    saida = tmp_path / "planta_acabamentos.dxf"
    n = gerar_dxf_acabamentos(arq, rel.acabamentos, saida)
    assert sum(len(geo["camadas"][g]["linhas"]) for g in geo["geradas"]) == n
