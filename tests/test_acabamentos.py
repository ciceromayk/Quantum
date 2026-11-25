"""Planta de acabamentos sintética, em metros, no padrão ArchiCAD do projeto real."""

import ezdxf
import pytest

from quantum.agentes.acabamentos import AgenteAcabamentos
from quantum.dxf_acabamentos import gerar_dxf_acabamentos
from quantum.orquestrador import analisar


def _etiqueta(doc, msp, x, y, piso, parede, teto, nome):
    b = doc.blocks.new(name=nome)
    for tag in ("A", "B", "C"):
        b.add_attdef(tag, (0, 0))
    ins = msp.add_blockref(nome, (0, 0), dxfattribs={"layer": "TEXTO"})
    for tag, txt, px, py in (("A", piso, x, y), ("B", parede, x + 0.32, y), ("C", teto, x, y - 0.24)):
        ins.add_attrib(tag, txt, (px, py))


def criar_planta_acabamentos(caminho, com_contorno=True):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    # Quadro: cabeçalho 5 m à direita da coluna de códigos, descrição 0,47 m à direita do código.
    for tipo, x0 in (("PISO", 100), ("PAREDE", 120), ("TETO", 140)):
        msp.add_mtext(f"ESPECIFICAÇÃO - {tipo}", dxfattribs={"layer": "TEXTO", "insert": (x0 + 5.15, 50)})
        for k, desc in enumerate((f"{tipo} UM", f"{tipo} DOIS")):
            msp.add_mtext(f"0{k + 1}", dxfattribs={"layer": "TEXTO", "insert": (x0, 49.55 - 0.3 * k)})
            msp.add_mtext(desc, dxfattribs={"layer": "TEXTO", "insert": (x0 + 0.47, 49.55 - 0.3 * k)})
    # SALA 3 x 4 m e BANHO 2 x 1,5 m; rótulos em MTEXT, etiquetas a ~0,3 m.
    for nome, (x, y, w, h), cods in (("SALA", (0, 0, 3, 4), ("01", "02", "02")), ("BANHO", (10, 0, 2, 1.5), ("02", "01", "01"))):
        if com_contorno:
            msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True, dxfattribs={"layer": "ZONA"})
        msp.add_mtext(f"{nome}\\P{w * h:.2f} m2".replace(".", ","), dxfattribs={"layer": "TEXTO", "insert": (x + 1, y + 1)})
        _etiqueta(doc, msp, x + 0.72, y + 1.07, *cods, nome=f"Rótulo_{nome}")
    # Ambiente sem etiqueta
    msp.add_mtext("DEPÓSITO\\P2,00 m2", dxfattribs={"layer": "TEXTO", "insert": (30, 0)})
    doc.saveas(caminho)


def _ac(rel):
    return {i.codigo: i for i in rel.itens if i.disciplina == "acabamentos"}


def test_le_quadro_etiquetas_e_mede(tmp_path):
    arq = tmp_path / "acab.dxf"
    criar_planta_acabamentos(arq)
    rel = analisar(arq, parametros={"pe_direito": 2.92, "espessura_laje": 0.12, "altura_parede_01": 1.2, "altura_parede_02": "teto"})
    cat = rel.acabamentos["catalogo"]
    assert cat["piso"] == {"01": "PISO UM", "02": "PISO DOIS"}
    assert cat["parede"]["02"] == "PAREDE DOIS"
    it = _ac(rel)
    assert it["ACB-PISO-01"].quantidade == pytest.approx(12.0)
    assert it["ACB-PISO-02"].quantidade == pytest.approx(3.0)
    assert it["ACB-TETO-02"].quantidade == pytest.approx(12.0)
    # parede 02 (SALA): perímetro 14 m × (pé-direito 2,92 − laje 0,12); parede 01 (BANHO): 7 m × 1,2
    assert it["ACB-PAREDE-02"].quantidade == pytest.approx(14 * 2.8)
    assert it["ACB-PAREDE-01"].quantidade == pytest.approx(7 * 1.2)
    msgs = " ".join(p.mensagem for p in rel.pendencias)
    assert "DEPÓSITO" in msgs  # sem etiqueta
    assert "cortes" in msgs  # aviso das alturas


def test_sem_altura_e_sem_contorno_viram_pendencia(tmp_path):
    arq = tmp_path / "acab.dxf"
    criar_planta_acabamentos(arq, com_contorno=False)
    rel = analisar(arq)
    it = _ac(rel)
    assert it["ACB-PISO-01"].quantidade == pytest.approx(12.0)  # área declarada no rótulo
    assert "declarada" in it["ACB-PISO-01"].observacao
    assert it["ACB-PAREDE-01"].quantidade is None
    bloq = [p.mensagem for p in rel.pendencias if p.severidade.value == "bloqueante" and p.disciplina == "acabamentos"]
    assert any("Parede 01" in m for m in bloq)


def test_gera_dxf_novo_sem_alterar_original(tmp_path):
    arq = tmp_path / "acab.dxf"
    criar_planta_acabamentos(arq)
    antes = arq.read_bytes()
    rel = analisar(arq)
    saida = tmp_path / "acab_quantum.dxf"
    assert gerar_dxf_acabamentos(arq, rel.acabamentos, saida) == 6
    assert arq.read_bytes() == antes
    novo = ezdxf.readfile(saida)
    pl = novo.modelspace().query('LWPOLYLINE[layer ? "QTD-PISO-01 .*"]')
    assert len(pl) == 1 and pl[0].closed
    # uma camada por acabamento, com o material no nome e na descrição
    camada = next(c for c in novo.layers if c.dxf.name.startswith("QTD-PAREDE-02"))
    assert camada.dxf.name == "QTD-PAREDE-02 PAREDE DOIS"
    assert camada.description == "PAREDE DOIS"
    with pytest.raises(ValueError):
        gerar_dxf_acabamentos(arq, rel.acabamentos, arq)


def criar_corte(caminho):
    """Corte em metros: BANHO com porcelanato (GRELHA) do piso até a laje, bancada a 0,82 m."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()

    def hachura(padrao, x0, y0, x1, y1):
        h = msp.add_hatch(dxfattribs={"layer": "HATCH 1"})
        h.set_pattern_fill(padrao, scale=0.1)
        h.paths.add_polyline_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], is_closed=True)

    hachura("CONCRETO_0002", -1, -0.07, 5, 0)  # contrapiso
    hachura("GRELHA_60X60_0002", 0, 0, 2, 0.82)
    hachura("GRELHA_60X60_0002", 0, 0.94, 2, 2.99)
    hachura("CONCRETO_CIA_0002", -1, 2.49, 5, 2.99)  # laje + forro em corte
    hachura("CONCRETO_0002", -1, 2.99, 5, 3.06)  # piso do andar de cima
    hachura("GRELHA_60X60_0002", 0, 3.06, 2, 6.05)  # andar de cima, sem nome: ignorado
    msp.add_mtext("BANHO", dxfattribs={"insert": (1, 1.5), "layer": "TEXTO"})
    msp.add_mtext("+3,06 (P.O.)", dxfattribs={"insert": (4, 3.1), "layer": "COTA"})
    doc.saveas(caminho)


def test_le_altura_do_corte(tmp_path):
    from quantum.cortes import ler_alturas_corte

    corte = tmp_path / "corte.dxf"
    criar_corte(corte)
    alt = ler_alturas_corte(corte)
    assert len(alt) == 1
    assert alt[0].ambiente == "BANHO"
    assert alt[0].altura_m == pytest.approx(2.49)
    assert alt[0].interrupcoes == [(0.82, 0.94)]

    planta = tmp_path / "acab.dxf"
    criar_planta_acabamentos(planta)
    rel = analisar(planta, cortes=[corte])
    it = _ac(rel)
    assert it["ACB-PAREDE-01"].quantidade == pytest.approx(7 * 2.49)  # BANHO, parede 01
    assert "corte" in it["ACB-PAREDE-01"].observacao
    assert it["ACB-PAREDE-02"].quantidade is None  # SALA não aparece no corte


def test_le_altura_de_corte_em_dxf_binario(tmp_path):
    from quantum.cortes import ler_alturas_corte

    ascii_ = tmp_path / "corte.dxf"
    criar_corte(ascii_)
    binario = tmp_path / "corte_bin.dxf"
    ezdxf.readfile(ascii_).saveas(binario, fmt="bin")
    assert binario.read_bytes().startswith(b"AutoCAD Binary DXF")
    alt = ler_alturas_corte(binario)
    assert [(a.ambiente, a.altura_m) for a in alt] == [("BANHO", pytest.approx(2.49))]


def test_altura_de_corte_casa_nome_parecido_do_ambiente():
    """O corte diz "COZ."; a planta diz "COZ. / SERV.": a altura é usada e fica o aviso."""
    from quantum.agentes.acabamentos import AgenteAcabamentos

    ag = AgenteAcabamentos({}, {}, {"COZ.": 2.49, "COPA": 2.34})
    assert ag._altura_de_corte("COZ. / SERV.") == 2.49
    assert ag._altura_de_corte("COPA") == 2.34  # igual continua igual
    assert ag.aproximados == {"COZ. / SERV.": "COZ."}
    assert ag._altura_de_corte("QUARTO") is None  # sem parentesco, sem altura
    assert ag._altura_de_corte("SUÍTE CASAL") is None


def test_altura_de_corte_nao_casa_quando_os_parecidos_divergem():
    from quantum.agentes.acabamentos import AgenteAcabamentos

    ag = AgenteAcabamentos({}, {}, {"COZ.": 2.49, "COZINHA GOURMET": 2.70})
    assert ag._altura_de_corte("COZ. / SERV.") is None  # dois candidatos, alturas diferentes
    assert not ag.aproximados


def test_nomes_de_corte_equivalentes_com_alturas_diferentes_nao_sao_usados():
    """"COZ." e "COZ" viram a mesma chave: com alturas diferentes, nenhuma vale."""
    ag = AgenteAcabamentos({}, {}, {"COZ.": 2.49, "COZ": 2.60})
    assert ag.alturas_corte == {}
    assert ag._altura_de_corte("COZ. / SERV.") is None
    assert "COZINHA" in ag.conflitos or "COZ" in ag.conflitos


def test_nomes_de_corte_equivalentes_com_a_mesma_altura_valem():
    ag = AgenteAcabamentos({}, {}, {"COZ.": 2.49, "COZ": 2.49})
    assert ag.conflitos == {}
    assert ag._altura_de_corte("COZ") == 2.49


def test_conflito_parecido_barra_o_casamento_por_aproximacao():
    """Com "COZ." 2,49 e "COZ" 2,60 no corte, "COZINHA GOURMET" não pode virar a resposta."""
    ag = AgenteAcabamentos({}, {}, {"COZ.": 2.49, "COZ": 2.60, "COZINHA GOURMET": 2.70})
    assert ag._altura_de_corte("COZ. / SERV.") is None
    assert ag.aproximados == {}


def test_corte_sem_todos_os_ambientes_avisa(tmp_path):
    arq, corte = tmp_path / "acab.dxf", tmp_path / "corte.dxf"
    criar_planta_acabamentos(arq)
    criar_corte(corte)
    rel = analisar(arq, cortes=[corte], parametros={"pe_direito": 2.92, "espessura_laje": 0.12})
    alerta = next(p for p in rel.pendencias if "não representam todos os ambientes" in p.mensagem)
    assert "SALA" in alerta.mensagem and "BANHO" not in alerta.mensagem
    assert "pé-direito − laje" in alerta.acao_sugerida
    # SALA preenchida à mão com pé-direito − laje: 14 m × 2,80
    rel = analisar(arq, cortes=[corte], parametros={"pe_direito": 2.92, "espessura_laje": 0.12, "altura_ambiente_SALA": "laje"})
    sala = next(a for a in rel.acabamentos["alturas_parede"] if a["nome"] == "SALA")
    assert sala["altura_m"] == pytest.approx(2.80) and sala["area_liquida_m2"] == pytest.approx(14 * 2.80)
    banho = next(a for a in rel.acabamentos["alturas_parede"] if a["nome"] == "BANHO")
    assert banho["origem_altura"] == "corte" and banho["altura_m"] == pytest.approx(2.49)
