import base64
import json

from quantum.navegador import processar_dxf


def test_processar_dxf_devolve_resultado_e_relatorios(planta):
    saida = json.loads(processar_dxf(str(planta), json.dumps({"pe_direito": 2.8})))
    assert saida["resultado"]["itens"]
    assert "ESTIMATIVA" in saida["markdown"].upper()
    assert base64.b64decode(saida["xlsx_base64"])[:2] == b"PK"
