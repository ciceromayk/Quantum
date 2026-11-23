import math

import pytest

from quantum import analisar
from quantum.cli import main
from quantum.modelos import Severidade


def _item(rel, codigo, detalhe=None):
    achados = [i for i in rel.itens if i.codigo == codigo and (detalhe is None or i.detalhe == detalhe)]
    assert achados, f"item {codigo} {detalhe} não encontrado"
    return achados[0]


def _tem(rel, trecho, sev=None):
    return any(trecho in p.mensagem and (sev is None or p.severidade == sev) for p in rel.pendencias)


def test_unidade_do_cabecalho(planta):
    rel = analisar(planta)
    assert rel.desenho.unidade == "mm"
    assert rel.desenho.fator_m == 0.001


def test_areas_por_ambiente_com_rotulo(planta):
    rel = analisar(planta)
    assert _item(rel, "ARQ-AMBIENTES", "SALA").quantidade == pytest.approx(20.0)
    assert _item(rel, "ARQ-AMBIENTES", "QUARTO").quantidade == pytest.approx(9.0)
    assert _item(rel, "ARQ-AMBIENTES", "total").quantidade == pytest.approx(29.0)


def test_area_escrita_divergente_vira_pendencia(planta):
    rel = analisar(planta)
    assert _tem(rel, "21,00 m²", Severidade.ALERTA)
    assert not _tem(rel, "9,00 m²")


def test_contorno_aberto_vira_pendencia(planta):
    rel = analisar(planta)
    assert _tem(rel, "contorno(s) aberto(s)")
    assert _tem(rel, "parecem fechados")


def test_comprimentos(planta):
    rel = analisar(planta)
    assert _item(rel, "ARQ-PAREDES").quantidade == pytest.approx(17.0)
    assert _item(rel, "ELE-ELETRODUTOS").quantidade == pytest.approx(6.0)
    assert _item(rel, "HID-AGUA-FRIA").quantidade == pytest.approx(3.5)
    assert _item(rel, "HID-ESGOTO").quantidade == pytest.approx(math.pi / 2, rel=1e-3)


def test_duplicatas_sao_apontadas(planta):
    rel = analisar(planta)
    assert _tem(rel, "ARQ-PAREDES: 1 elemento(s) sobreposto")
    assert _tem(rel, "ELE-TOMADAS: 1 elemento(s) sobreposto")


def test_contagem_por_bloco(planta):
    rel = analisar(planta)
    assert _item(rel, "ELE-TOMADAS", "bloco TUG").quantidade == 4
    assert _item(rel, "ELE-ILUMINACAO", "bloco LUM").quantidade == 2
    assert _item(rel, "ARQ-PORTAS", "bloco PORTA80").quantidade == 1


def test_ponto_sem_bloco_em_camada_de_contagem_vira_pendencia(planta):
    rel = analisar(planta)
    assert _tem(rel, "ELE-TOMADAS: 1 entidade(s) sem bloco", Severidade.ALERTA)
    assert "POINT" in next(p.mensagem for p in rel.pendencias if p.mensagem.startswith("ELE-TOMADAS: 1 entidade"))


def test_pilares_e_derivado_sem_parametro(planta):
    rel = analisar(planta)
    assert _item(rel, "EST-PILARES-UN").quantidade == 2
    assert _item(rel, "EST-PILARES", "total").quantidade == pytest.approx(0.16)
    assert _item(rel, "EST-PILARES-CONCRETO").quantidade is None
    assert _tem(rel, "altura_pilar", Severidade.BLOQUEANTE)


def test_derivado_com_parametro(planta):
    rel = analisar(planta, parametros={"altura_pilar": 3.0, "pe_direito": 2.8})
    assert _item(rel, "EST-PILARES-CONCRETO").quantidade == pytest.approx(0.48)
    assert _item(rel, "ARQ-PAREDES-AREA").quantidade == pytest.approx(17.0 * 2.8)
    assert not _tem(rel, "altura_pilar")


def test_camada_nao_classificada(planta):
    rel = analisar(planta)
    assert "PAISAGISMO" in rel.camadas_nao_classificadas
    assert "ARQ-TEXTO" not in rel.camadas_nao_classificadas


def test_sem_unidade_nao_adivinha(planta_sem_unidade):
    rel = analisar(planta_sem_unidade)
    assert rel.desenho.unidade is None
    assert _item(rel, "ARQ-PAREDES").quantidade is None
    assert _tem(rel, "não declara unidade", Severidade.BLOQUEANTE)


def test_sem_unidade_com_unidade_informada(planta_sem_unidade):
    rel = analisar(planta_sem_unidade, unidade="mm")
    assert _item(rel, "ARQ-PAREDES").quantidade == pytest.approx(17.0)


def test_orcamento(planta, tmp_path):
    tabela = tmp_path / "precos.csv"
    tabela.write_text(
        "item_quantum;detalhe;codigo_ref;descricao;unidade;preco_unitario;fonte;data_base\n"
        "ELE-TOMADAS;;REF-1;Ponto de tomada;un;100,00;Teste;11/2026\n"
        "ARQ-AMBIENTES;;REF-2;Piso;m2;50,00;Teste;11/2026\n"
        "HID-AGUA-FRIA;;REF-3;Tubo;m²;10,00;Teste;11/2026\n"
        "EST-PILARES-CONCRETO;;REF-4;Concreto;m³;800,00;Teste;11/2026\n",
        encoding="utf-8",
    )
    rel = analisar(planta, tabela_precos=tabela, bdi=25)
    por_cod = {o.codigo_quantum: o for o in rel.orcamento}
    assert por_cod["ELE-TOMADAS"].total == pytest.approx(400.0)
    assert por_cod["ARQ-AMBIENTES"].total == pytest.approx(29.0 * 50)  # só o total, sem somar ambientes 2x
    assert "HID-AGUA-FRIA" not in por_cod  # unidade errada
    assert _tem(rel, "unidade da tabela", Severidade.BLOQUEANTE)
    assert "EST-PILARES-CONCRETO" not in por_cod  # sem altura_pilar
    assert rel.total_orcamento == pytest.approx(400 + 1450)


def test_cli_gera_arquivos(planta, tmp_path, capsys):
    saida = tmp_path / "out"
    assert main(["analisar", str(planta), "--saida", str(saida), "--param", "pe_direito=2,80"]) == 0
    assert (saida / "planta.md").exists()
    assert (saida / "planta.xlsx").exists()
    assert (saida / "planta.json").exists()
    md = (saida / "planta.md").read_text(encoding="utf-8")
    assert "ESTIMATIVAS TÉCNICAS" in md
    assert "### Elétrica" in md


def test_dwg_sem_oda_da_mensagem_clara(tmp_path):
    from quantum.ingestao import ErroIngestao, abrir_documento

    f = tmp_path / "x.dwg"
    f.write_bytes(b"AC1032")
    with pytest.raises(ErroIngestao):
        abrir_documento(f)


def test_nome_de_bloco_sem_sufixo_de_instancia():
    from quantum.ingestao import nome_tipo_bloco

    assert nome_tipo_bloco("Vaso Sanitário 26[3]_1") == "Vaso Sanitário"
    assert nome_tipo_bloco("TORNEIRA DE BICA ALTA PARA LAVATÓRIO[20]_1") == "TORNEIRA DE BICA ALTA PARA LAVATÓRIO"
    assert nome_tipo_bloco("BHO._32_5_1") == "BHO."
    assert nome_tipo_bloco("Rótulo_12_1") == "Rótulo"
    assert nome_tipo_bloco("PORTA_80_210") == "PORTA_80_210"  # medida no nome não é sufixo


def test_rotulo_de_ambiente_em_bloco(tmp_path):
    import ezdxf

    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    b = doc.blocks.new("Rótulo_1_1")
    b.add_mtext("SUÍTE CASAL^ ^ ^", dxfattribs={"layer": "TEXTO"})
    b.add_mtext("11,05^  m2^ ^", dxfattribs={"layer": "TEXTO"})
    msp = doc.modelspace()
    msp.add_blockref("Rótulo_1_1", (0, 0), dxfattribs={"layer": "TEXTO"})
    # BIM exporta blocos diferentes no mesmo ponto (0,0): não são duplicatas
    for n in (1, 2):
        doc.blocks.new(f"Porta 26[{n}]_1").add_line((n, 0), (n + 1, 0))
        msp.add_blockref(f"Porta 26[{n}]_1", (0, 0), dxfattribs={"layer": "ESQ"})
    f = tmp_path / "bim.dxf"
    doc.saveas(f)
    rel = analisar(f)
    assert _item(rel, "ARQ-AMBIENTES-ROTULO", "SUÍTE CASAL").quantidade == pytest.approx(11.05)
    assert _item(rel, "ARQ-ESQUADRIAS", "bloco Porta").quantidade == 2
    assert not _tem(rel, "sobreposto")
