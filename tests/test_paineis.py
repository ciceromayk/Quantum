"""Planta falada sintética (metros) no padrão do escritório: camada por sistema de parede."""

import ezdxf
import pytest

from quantum.agentes.paineis import especificacao_da_camada, faces
from quantum.orquestrador import analisar
from quantum.relatorio import para_xlsx


def criar_planta_falada(caminho):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4  # o cabeçalho diz mm, mas o desenho está em metros (como no arquivo real)
    msp = doc.modelspace()

    def parede(camada, pts):
        msp.add_lwpolyline(pts, dxfattribs={"layer": camada})

    def texto(t, x, y, rot=0, camada="ARQ"):
        msp.add_text(t, dxfattribs={"insert": (x, y), "rotation": rot, "layer": camada, "height": 0.2})

    # duas unidades lado a lado (COLUNA 01 e 02), iguais: suíte com drywall 70 ST+ST de 4 m
    for x0, col in ((0, "01"), (10, "02")):
        parede("0_DRY_WALL_70mm_+ST+ST", [(x0, 0), (x0 + 4, 0)])
        texto("SUÍTE 01", x0 + 2, 1.0)
        texto("10,00", x0 + 2, 0.6)
        texto(f"COLUNA {col}", x0 + 2, -5)  # rótulo da coluna abaixo do prédio
    # alvenaria de 14 cm na fachada (20 m) com a porta de correr P15 (2,40 × 2,20 = 5,28 m²: desconta)
    # e a porta P01 (0,64 × 2,12 = 1,36 m²: entra cheia)
    parede("0_TIJOLO CERAMICO_14CM", [(0, 3), (20, 3)])
    texto("P15", 5, 3.3)
    texto("P01", 15, 3.3)
    # tijolo de 19 cm sob viga: nota H=2,28M ligada à parede por chamada com círculo
    parede("0_TIJOLO CERAMICO_19CM", [(0, 6), (3, 6)])
    texto("H=2,28M", 6, 8, camada="OBSERVAÇÕES")
    msp.add_line((7.2, 8.1), (1.5, 6.0), dxfattribs={"layer": "OBSERVAÇÕES"})
    msp.add_circle((7.2, 8.1), 0.12, dxfattribs={"layer": "OBSERVAÇÕES"})
    # legenda: amostras nas mesmas camadas, dentro do quadro (não medem)
    for k, cam in enumerate(("0_DRY_WALL_70mm_+ST+ST", "0_TIJOLO CERAMICO_14CM")):
        parede(cam, [(-30, 20 - k), (-28, 20 - k)])
    msp.add_lwpolyline([(-32, 15), (-25, 15), (-25, 22), (-32, 22)], close=True, dxfattribs={"layer": "QUADRO DE ALVENARIAS"})
    doc.saveas(caminho)


PAR = {"pe_esquerdo": 2.88, "contrapiso": 0.05, "espessura_laje": 0.20,
       "vao_P15_largura": 2.40, "vao_P15_altura": 2.20, "vao_P01_largura": 0.64, "vao_P01_altura": 2.12,
       "_pavimento": "TIPO A"}


def test_camadas_e_faces():
    assert especificacao_da_camada("0_DRY_WALL_70mm_+ST+ST") == "PERFIL 70MM + ST + ST"
    assert especificacao_da_camada("0_STEEL_FRAME_90MM + GR + ST") == "PERFIL STEEL FRAME 90MM + GR + ST"
    assert especificacao_da_camada("0_TIJOLO CERÂMICO_9CM") == "ALVENARIA TIJOLO DE 9CM"
    assert especificacao_da_camada("ALVENARIA") is None
    assert faces("PERFIL 70MM + ST + RU") == {"ST": 1, "RU": 1}
    assert faces("PERFIL 70MM + RU + RU") == {"RU": 2}


def test_planilha_da_planta_falada(tmp_path):
    arq = tmp_path / "falada.dxf"
    criar_planta_falada(arq)
    rel = analisar(arq, parametros=PAR)
    linhas = rel.paineis["linhas"]
    assert rel.paineis["pavimento"] == "TIPO A"
    # unidades iguais viram uma linha com QTDE 2
    st = next(l for l in linhas if l["especificacao"] == "PERFIL 70MM + ST + ST")
    assert st["coluna"] == "COLUNA 01/02" and st["qtde"] == 2 and st["ambiente"] == "SUÍTES"
    assert st["perimetro_m"] == pytest.approx(4.0)
    assert st["altura_m"] == pytest.approx(2.63)  # 2,88 − 0,05 − 0,20
    assert st["area_total_m2"] == pytest.approx(2 * 4 * 2.63)
    # vão acima de 2 m² desconta a área total; o de até 2 m² entra cheio
    t14 = next(l for l in linhas if l["especificacao"] == "ALVENARIA TIJOLO DE 14CM")
    assert t14["esquadrias"] == "P15" and t14["area_esquadrias_m2"] == pytest.approx(5.28)
    assert t14["area_total_m2"] == pytest.approx(20 * 2.63 - 5.28)
    assert t14["coluna"] == "GERAL"
    # nota H=2,28M: altura livre sob viga de 0,60, menos o contrapiso
    t19 = next(l for l in linhas if l["especificacao"] == "ALVENARIA TIJOLO DE 19CM")
    assert t19["elemento"] == "VIGA" and t19["altura_elemento"] == pytest.approx(0.60)
    assert t19["altura_m"] == pytest.approx(2.23)
    msgs = " ".join(p.mensagem for p in rel.pendencias if p.disciplina == "paredes")
    assert "legenda" in msgs and "METROS" in msgs
    it = {i.codigo: i.quantidade for i in rel.itens if i.disciplina == "paredes"}
    assert it["INS-CHAPA-ST-(M2)"] == pytest.approx(2 * 2 * 4 * 2.63)  # duas faces ST
    assert it["INS-MARCACAO-DE-TIJOLO-CERAMICO-(M)"] == pytest.approx(23.0)
    para_xlsx(rel, tmp_path / "saida.xlsx")
    from openpyxl import load_workbook

    wb = load_workbook(tmp_path / "saida.xlsx")
    ws = wb["Paredes e Paineis"]
    assert ws["H5"].value == "ESPECIFICAÇÃO" and ws["U5"].value == "ÁREA TOTAL (M2)"
    assert "Resumo Paredes" in wb.sheetnames


def test_sem_quadro_vira_pendencia(tmp_path):
    arq = tmp_path / "falada.dxf"
    criar_planta_falada(arq)
    rel = analisar(arq, parametros={k: v for k, v in PAR.items() if not k.startswith("vao_P15")})
    bloq = [p.mensagem for p in rel.pendencias if p.disciplina == "paredes" and p.severidade.value == "bloqueante"]
    assert any("P15" in m for m in bloq)
    ids = {e["id"] for e in rel.paineis["esquadrias"]}
    assert ids == {"P15", "P01"}


def test_repeticoes_do_pavimento(tmp_path):
    arq = tmp_path / "falada.dxf"
    criar_planta_falada(arq)
    rel = analisar(arq, parametros={**PAR, "_repeticoes": 3})
    st = next(l for l in rel.paineis["linhas"] if l["especificacao"] == "PERFIL 70MM + ST + ST")
    assert st["rep"] == 3 and st["area_total_m2"] == pytest.approx(3 * 2 * 4 * 2.63)
    it = {i.codigo: i.quantidade for i in rel.itens if i.disciplina == "paredes"}
    assert it["INS-MARCACAO-DE-TIJOLO-CERAMICO-(M)"] == pytest.approx(3 * 23.0)


def test_id_em_atributo_e_chamada_em_mm(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    blk = doc.blocks.new("ETIQ")
    blk.add_attdef("ID", (0, 0), dxfattribs={"height": 200})
    msp.add_lwpolyline([(0, 3000), (20000, 3000)], dxfattribs={"layer": "0_TIJOLO CERAMICO_14CM"})
    msp.add_blockref("ETIQ", (5000, 3300)).add_auto_attribs({"ID": "P15"})
    msp.add_lwpolyline([(0, 6000), (3000, 6000)], dxfattribs={"layer": "0_TIJOLO CERAMICO_19CM"})
    msp.add_text("H=2,28M", dxfattribs={"insert": (6000, 8000), "height": 200, "layer": "OBSERVAÇÕES"})
    msp.add_line((7200, 8100), (1500, 6000), dxfattribs={"layer": "OBSERVAÇÕES"})
    msp.add_circle((7200, 8100), 120, dxfattribs={"layer": "OBSERVAÇÕES"})
    arq = tmp_path / "mm.dxf"
    doc.saveas(arq)
    rel = analisar(arq, parametros=PAR)
    linhas = rel.paineis["linhas"]
    t14 = next(l for l in linhas if l["especificacao"] == "ALVENARIA TIJOLO DE 14CM")
    assert t14["esquadrias"] == "P15" and t14["perimetro_m"] == pytest.approx(20.0)
    t19 = next(l for l in linhas if l["especificacao"] == "ALVENARIA TIJOLO DE 19CM")
    assert t19["elemento"] == "VIGA" and t19["altura_m"] == pytest.approx(2.23)


def test_parede_baixa_pelo_texto_do_desenho(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (10, 0)], dxfattribs={"layer": "0_TIJOLO CERAMICO_14CM"})  # mureta
    msp.add_lwpolyline([(0, 5), (10, 5)], dxfattribs={"layer": "0_TIJOLO CERAMICO_14CM"})  # parede cheia
    msp.add_lwpolyline([(0, 10), (10, 10)], dxfattribs={"layer": "0_TIJOLO CERAMICO_19CM"})  # guarda-corpo ambíguo
    msp.add_text("MURETA h=0,20m (ACABADO)", dxfattribs={"insert": (4, 0.3), "height": 0.15})
    msp.add_text("MURETA h=0,20m", dxfattribs={"insert": (4, 6.5), "height": 0.15})  # a 1,5 m: não vale
    msp.add_text("GUARDA-CORPO h=1,00m + MURETA", dxfattribs={"insert": (4, 10.3), "height": 0.15})
    arq = tmp_path / "baixa.dxf"
    doc.saveas(arq)
    rel = analisar(arq, parametros=PAR)
    linhas = rel.paineis["linhas"]
    baixa = next(l for l in linhas if l["origem_altura"] == "texto do desenho")
    assert baixa["altura_m"] == pytest.approx(0.20) and baixa["perimetro_m"] == pytest.approx(10.0)
    assert baixa["area_total_m2"] == pytest.approx(2.0)
    assert "MURETA h=0,20m (ACABADO)" in baixa["elemento"]
    cheias = [l for l in linhas if l["origem_altura"] != "texto do desenho"]
    assert cheias and all(l["altura_m"] == pytest.approx(2.63) for l in cheias)  # sem texto perto: pé-esquerdo − contrapiso − laje
    msgs = " ".join(p.mensagem for p in rel.pendencias if p.disciplina == "paredes")
    assert "TEXTO DO DESENHO" in msgs and "guarda-corpo e mureta" in msgs
    from quantum.relatorio import para_markdown

    assert "texto do desenho: MURETA h=0,20m (ACABADO)" in para_markdown(rel)
    para_xlsx(rel, tmp_path / "s.xlsx")
    from openpyxl import load_workbook

    ws = load_workbook(tmp_path / "s.xlsx")["Paredes e Paineis"]
    r = next(r for r in range(6, ws.max_row + 1) if "MURETA" in str(ws.cell(r, 14).value))
    assert ws.cell(r, 12).value == pytest.approx(0.20) and ws.cell(r, 13).value == 0 and ws.cell(r, 15).value == 0


def test_nome_do_ambiente_em_texto_misto_com_mureta(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (4, 0)], dxfattribs={"layer": "0_BLOCO DE CONCRETO_14CM"})
    msp.add_mtext("ESCADA\\PMURETA h=0,20m", dxfattribs={"insert": (2, 0.4), "char_height": 0.15})
    arq = tmp_path / "misto.dxf"
    doc.saveas(arq)
    l = analisar(arq, parametros=PAR).paineis["linhas"][0]
    assert l["classificacao"] == "CX DE ESCADA" and l["altura_m"] == pytest.approx(0.20)
