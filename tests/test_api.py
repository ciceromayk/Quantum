import pytest
from fastapi.testclient import TestClient

from quantum_api import criar_app
from quantum_api.config import Config


@pytest.fixture
def cliente(tmp_path):
    cfg = Config(
        database_url=f"sqlite:///{tmp_path / 'q.db'}",
        pasta_arquivos=tmp_path / "arquivos",
        tamanho_max_mb=5,
    )
    with TestClient(criar_app(cfg), base_url="http://testserver/api") as c:
        yield c


def _projeto_pavimento(c, repeticoes=14):
    p = c.post("/projetos", json={"nome": "Edifício Teste", "data_base": "11/2026"}).json()
    pav = c.post(f"/projetos/{p['id']}/pavimentos", json={"nome": "Tipo", "repeticoes": repeticoes}).json()
    return p, pav


def _enviar(c, pav_id, caminho, nome="planta.dxf"):
    with open(caminho, "rb") as f:
        return c.post(f"/pavimentos/{pav_id}/arquivos", files={"arquivo": (nome, f, "application/dxf")})


def test_saude_traz_aviso(cliente):
    r = cliente.get("/saude").json()
    assert r["status"] == "ok"
    assert "ESTIMATIVAS" in r["aviso"]


def test_fluxo_completo(cliente, planta):
    p, pav = _projeto_pavimento(cliente)
    r = _enviar(cliente, pav["id"], planta)
    assert r.status_code == 202
    analise = r.json()
    assert analise["revisao"] == 1

    det = cliente.get(f"/analises/{analise['id']}").json()
    assert det["status"] == "concluida", det["erro"]
    assert det["pendencias_por_severidade"]["bloqueante"] >= 1
    codigos = {i["codigo"] for i in det["resultado"]["itens"]}
    assert {"ARQ-AMBIENTES", "ELE-TOMADAS", "EST-PILARES"} <= codigos

    proj = cliente.get(f"/projetos/{p['id']}").json()
    assert proj["pavimentos"][0]["analises"][0]["status"] == "concluida"

    xlsx = cliente.get(f"/analises/{analise['id']}/relatorio.xlsx")
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"
    md = cliente.get(f"/analises/{analise['id']}/relatorio.md").text
    assert "ESTIMATIVAS TÉCNICAS" in md


def test_parametros_e_reprocessamento(cliente, planta):
    _, pav = _projeto_pavimento(cliente)
    a = _enviar(cliente, pav["id"], planta).json()
    r = cliente.put(f"/pavimentos/{pav['id']}/parametros", json={"valores": {"altura_pilar": 3.0}})
    assert r.status_code == 200
    assert cliente.post(f"/analises/{a['id']}/reprocessar").status_code == 202
    itens = cliente.get(f"/analises/{a['id']}").json()["resultado"]["itens"]
    vol = next(i for i in itens if i["codigo"] == "EST-PILARES-CONCRETO")
    assert vol["quantidade"] == pytest.approx(0.48)


def test_parametro_invalido(cliente):
    _, pav = _projeto_pavimento(cliente)
    r = cliente.put(f"/pavimentos/{pav['id']}/parametros", json={"valores": {"pe_direito": -1}})
    assert r.status_code == 422


def test_unidade_informada_no_pavimento(cliente, planta_sem_unidade):
    _, pav = _projeto_pavimento(cliente)
    a = _enviar(cliente, pav["id"], planta_sem_unidade).json()
    itens = cliente.get(f"/analises/{a['id']}").json()["resultado"]["itens"]
    assert next(i for i in itens if i["codigo"] == "ARQ-PAREDES")["quantidade"] is None
    cliente.put(f"/pavimentos/{pav['id']}/parametros", json={"valores": {}, "unidade": "mm"})
    cliente.post(f"/analises/{a['id']}/reprocessar")
    itens = cliente.get(f"/analises/{a['id']}").json()["resultado"]["itens"]
    assert next(i for i in itens if i["codigo"] == "ARQ-PAREDES")["quantidade"] == pytest.approx(17.0)


def test_revisoes_incrementam(cliente, planta):
    _, pav = _projeto_pavimento(cliente)
    assert _enviar(cliente, pav["id"], planta).json()["revisao"] == 1
    assert _enviar(cliente, pav["id"], planta).json()["revisao"] == 2


def test_dwg_recusado_com_orientacao(cliente, tmp_path):
    _, pav = _projeto_pavimento(cliente)
    f = tmp_path / "x.dwg"
    f.write_bytes(b"AC1027")
    r = _enviar(cliente, pav["id"], f, nome="x.dwg")
    assert r.status_code == 415
    assert "DXF" in r.json()["detail"]


def test_dxf_corrompido_vira_erro_registrado(cliente, tmp_path):
    _, pav = _projeto_pavimento(cliente)
    f = tmp_path / "ruim.dxf"
    f.write_text("isto não é um dxf")
    a = _enviar(cliente, pav["id"], f, nome="ruim.dxf").json()
    det = cliente.get(f"/analises/{a['id']}").json()
    assert det["status"] == "erro"
    assert det["erro"]


def test_arquivo_grande_recusado(cliente, tmp_path):
    _, pav = _projeto_pavimento(cliente)
    f = tmp_path / "grande.dxf"
    f.write_bytes(b"0" * (6 * 1024 * 1024))
    assert _enviar(cliente, pav["id"], f, nome="grande.dxf").status_code == 413


def test_404(cliente):
    assert cliente.get("/projetos/999").status_code == 404
    assert cliente.post("/projetos/999/pavimentos", json={"nome": "X"}).status_code == 404


def test_interface_web_servida_na_raiz(tmp_path):
    web = tmp_path / "dist"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>Quantum</title>")
    cfg = Config(
        database_url=f"sqlite:///{tmp_path / 'q.db'}",
        pasta_arquivos=tmp_path / "arquivos",
        tamanho_max_mb=5,
        pasta_web=web,
    )
    with TestClient(criar_app(cfg)) as c:
        assert "Quantum" in c.get("/").text
        assert c.get("/api/saude").json()["status"] == "ok"


def test_analise_presa_apos_reinicio_pode_ser_reprocessada(tmp_path, planta):
    cfg = Config(
        database_url=f"sqlite:///{tmp_path / 'q.db'}",
        pasta_arquivos=tmp_path / "arquivos",
        tamanho_max_mb=5,
    )
    with TestClient(criar_app(cfg), base_url="http://testserver/api") as c:
        _, pav = _projeto_pavimento(c)
        a = _enviar(c, pav["id"], planta).json()
    # simula um reinício no meio do processamento
    from quantum_api.db import Analise, criar_sessoes

    sessoes = criar_sessoes(cfg.database_url)
    with sessoes() as s:
        s.get(Analise, a["id"]).status = "processando"
        s.commit()
    with TestClient(criar_app(cfg), base_url="http://testserver/api") as c:
        det = c.get(f"/analises/{a['id']}").json()
        assert det["status"] == "erro"
        assert "Reprocessar" in det["erro"]
        assert c.post(f"/analises/{a['id']}/reprocessar").status_code == 202
        assert c.get(f"/analises/{a['id']}").json()["status"] == "concluida"
