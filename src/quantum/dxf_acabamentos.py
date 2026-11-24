"""Gera um DXF NOVO com polilinhas fechadas por acabamento. O arquivo original não é alterado.

O arquivo é montado do zero (ezdxf.new, AutoCAD 2013) e recebe uma cópia do Model do desenho
original pelo Importer do ezdxf: só entidades, blocos, camadas, tipos de linha e estilos usados.
Assim não herda objetos estranhos do arquivo de origem (por exemplo, um DXF convertido de DWG
pelo LibreDWG, que o AutoCAD recusa abrir). Entidades que o Importer não sabe copiar ficam de
fora (o contorno e a planta de referência continuam lá).

Para cada ambiente com contorno e etiqueta, cria uma LWPOLYLINE fechada em cada camada
QTD-PISO-<código>, QTD-PAREDE-<código> e QTD-TETO-<código>. A descrição do quadro de
acabamentos vai na descrição da camada. Contornos com divisa proposta (ambientes integrados
sem linha de divisão) vão em QTD-<tipo>-<código>-PROPOSTA, para conferência.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.addons.importer import IMPORT_ENTITIES, Importer

from .ingestao import abrir_documento

CORES = {"piso": 3, "parede": 1, "teto": 5}  # verde, vermelho, azul (ACI)
VERSAO = "R2013"  # AutoCAD 2013: abre em qualquer AutoCAD/LT atual e nos leitores livres


def _texto_seguro(t: str, limite: int = 200) -> str:
    """Descrição de camada numa linha só, sem caracteres de controle."""
    t = " ".join(str(t).split())
    return "".join(c for c in t if c.isprintable())[:limite]


def _documento_limpo(origem: str | Path):
    """Documento novo com a cópia do Model do original (sem layouts, objetos e XDATA de terceiros)."""
    fonte = abrir_documento(origem)
    doc = ezdxf.new(VERSAO, setup=True)
    for var in ("$INSUNITS", "$MEASUREMENT", "$LUNITS", "$LUPREC", "$AUNITS", "$INSBASE"):
        if var in fonte.header:
            try:
                doc.header[var] = fonte.header[var]
            except Exception:
                pass
    imp = Importer(fonte, doc)
    msp = doc.modelspace()
    for e in fonte.modelspace():
        tipo = e.dxftype()
        try:
            if tipo == "WIPEOUT":
                _copiar_mascara(e, doc, msp)
            elif tipo in IMPORT_ENTITIES and tipo != "DIMENSION":
                imp.import_entity(e)
            else:
                # Cota, multilinha, chamada, tabela etc.: entram explodidas (linhas, textos,
                # sólidos). O Importer perde o bloco de geometria da cota, e o AutoCAD
                # rejeita cota sem esse bloco.
                imp.import_entities(list(e.virtual_entities()))
        except Exception:
            continue  # sem representação copiável (sólido 3D, região, luz...): fica de fora
    imp.finalize()
    return doc


def _copiar_mascara(w, doc, msp) -> None:
    """WIPEOUT (máscara) não passa pelo Importer: recria pelo contorno, na mesma camada."""
    pts = [(v.x, v.y) for v in w.boundary_path_wcs()]
    if len(pts) < 3:
        return
    camada = w.dxf.get("layer", "0")
    if camada not in doc.layers:
        doc.layers.add(camada)
    msp.add_wipeout(pts, dxfattribs={"layer": camada})


def gerar_dxf_acabamentos(origem: str | Path, acabamentos: dict, saida: str | Path) -> int:
    """Devolve o número de polilinhas criadas. Não grava nada se nenhum ambiente tem contorno."""
    ambientes = [a for a in acabamentos.get("ambientes", []) if a.get("contorno") and a.get("codigos")]
    if not ambientes:
        return 0
    if Path(origem).resolve() == Path(saida).resolve():
        raise ValueError("O DXF gerado precisa ter outro nome: o original não é alterado.")
    doc = _documento_limpo(origem)
    msp = doc.modelspace()
    catalogo = acabamentos.get("catalogo", {})
    n = 0
    for a in ambientes:
        for tipo, cod in sorted(a["codigos"].items()):
            if tipo not in CORES:
                continue
            nome = f"QTD-{tipo.upper()}-{cod}" + ("-PROPOSTA" if a.get("contorno_origem") == "proposta" else "")
            if nome not in doc.layers:
                camada = doc.layers.add(nome, color=CORES[tipo])
                camada.description = _texto_seguro(catalogo.get(tipo, {}).get(cod, ""))
            pts = [tuple(p) for p in a["contorno"]]
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts = pts[:-1]
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": nome})
            n += 1
    doc.audit()
    doc.saveas(saida)
    return n
