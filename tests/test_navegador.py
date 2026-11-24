import base64
import json

from quantum.navegador import processar_dxf


def test_processar_dxf_devolve_resultado_e_relatorios(planta):
    saida = json.loads(processar_dxf(str(planta), json.dumps({"pe_direito": 2.8})))
    assert saida["resultado"]["itens"]
    assert "ESTIMATIVA" in saida["markdown"].upper()
    assert base64.b64decode(saida["xlsx_base64"])[:2] == b"PK"
    geo = saida["geometria"]
    assert geo["pontos"] > 0 and len(geo["caixa"]) == 4 and geo["camadas"]


def test_le_so_o_model(tmp_path):
    import ezdxf

    from quantum.orquestrador import analisar

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    doc.modelspace().add_lwpolyline([(0, 0), (4, 0), (4, 3), (0, 3)], close=True, dxfattribs={"layer": "PAREDE"})
    folha = doc.layouts.new("A1")
    folha.add_lwpolyline([(0, 0), (40, 0), (40, 30), (0, 30)], close=True, dxfattribs={"layer": "CARIMBO"})
    folha.add_text("CARIMBO", dxfattribs={"layer": "CARIMBO"})
    arq = tmp_path / "com_prancha.dxf"
    doc.saveas(arq)
    rel = analisar(arq)
    assert "CARIMBO" not in rel.desenho.camadas
    assert all(e.camada != "CARIMBO" for e in rel.desenho.entidades)
    assert any("Lido só o Model" in p.mensagem for p in rel.pendencias)
    geo = json.loads(processar_dxf(str(arq)))["geometria"]
    assert "CARIMBO" not in geo["camadas"]


def test_geometria_herda_camada_do_bloco_e_mostra_atributos(tmp_path):
    import ezdxf

    from quantum.ingestao import carregar
    from quantum.visualizacao import geometria

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("PORTAS", color=1)
    b = doc.blocks.new("PORTA")
    b.add_line((0, 0), (0.8, 0))  # camada 0: herda PORTAS
    b.add_line((0, 0), (0, 0.8), dxfattribs={"layer": "BATENTE"})
    b.add_attdef("COD", (0, 0))
    ins = doc.modelspace().add_blockref("PORTA", (5, 5), dxfattribs={"layer": "PORTAS"})
    ins.add_attrib("COD", "P1", (5, 5))
    arq = tmp_path / "porta.dxf"
    doc.saveas(arq)
    d = carregar(arq)
    g = geometria(d.modelspace, 1.0)
    assert set(g["camadas"]) == {"PORTAS", "BATENTE"}
    assert g["camadas"]["PORTAS"]["cor"] == "#ff0000"
    assert any(t[3] == "P1" for t in g["textos"])
