"""Gera um DXF NOVO com polilinhas fechadas por acabamento. O arquivo original não é alterado.

O arquivo é montado do zero (ezdxf.new, AutoCAD 2013) e recebe uma cópia do Model do desenho
original pelo Importer do ezdxf: só entidades, blocos, camadas, tipos de linha e estilos usados.
Assim não herda objetos estranhos do arquivo de origem (por exemplo, um DXF convertido de DWG
pelo LibreDWG, que o AutoCAD recusa abrir). Entidades que o Importer não sabe copiar ficam de
fora (o contorno e a planta de referência continuam lá).

Para cada ambiente com contorno e etiqueta:
- piso e teto (QTD-PISO-<código>, QTD-TETO-<código>): uma LWPOLYLINE fechada, que é a área;
- parede (QTD-PAREDE-<código>): uma LWPOLYLINE aberta em cada trecho colado a uma parede. As
  divisas com o ambiente vizinho (linha de projeção ou divisa proposta) não são parede e ficam
  de fora, então a soma dos comprimentos é o perímetro que entra no revestimento.

Todas saem com a largura de LARGURA_M (2,5 cm no desenho), para aparecerem na planta.

Há uma camada por acabamento (um código do quadro), com o material no nome e na descrição, e
uma cor própria: `QTD-PISO-01 PORCELANATO ELIANE MUNARI MARFIM AC 60 x 60 cm`. Contornos com
divisa proposta (ambientes integrados sem linha de divisão) vão para a camada equivalente com
`-PROPOSTA` depois do código, para conferência.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.addons.importer import IMPORT_ENTITIES, Importer

from .ingestao import abrir_documento

# Uma cor por acabamento, na faixa do tipo (ACI): piso em verde, parede em vermelho, teto em azul.
CORES = {
    "piso": (3, 92, 82, 72, 62, 102),
    "parede": (1, 11, 21, 241, 231, 221),
    "teto": (5, 141, 151, 161, 171, 181),
}
# o AutoCAD não aceita estes caracteres em nome de camada; os que separam número viram ponto
PROIBIDOS = {ord(c): None for c in '<>"?*|=`'} | {ord(c): "." for c in ",;:"} | {ord(c): "-" for c in "/\\"}
LIMITE_NOME = 100
VERSAO = "R2013"  # AutoCAD 2013: abre em qualquer AutoCAD/LT atual e nos leitores livres
LARGURA_M = 0.025  # espessura da polilinha, em metros (convertida para a unidade do desenho)


def _texto_seguro(t: str, limite: int = 200) -> str:
    """Descrição de camada numa linha só, sem caracteres de controle."""
    t = " ".join(str(t).split())
    return "".join(c for c in t if c.isprintable())[:limite]


def _nome_camada(tipo: str, cod: str, material: str, proposta: bool) -> str:
    """Camada do acabamento, com o material no nome: `QTD-PISO-01 PORCELANATO ELIANE ...`."""
    base = f"QTD-{tipo.upper()}-{cod}" + ("-PROPOSTA" if proposta else "")
    material = _texto_seguro(material).translate(PROIBIDOS).strip()
    base = base.translate(PROIBIDOS)
    nome = f"{base} {material}".strip() if material else base
    return nome[:LIMITE_NOME].strip()


def _cor(tipo: str, cod: str, codigos: dict[str, list[str]]) -> int:
    """Cor da camada: uma por código, dentro da faixa do tipo."""
    faixa = CORES[tipo]
    try:
        i = codigos[tipo].index(cod)
    except (KeyError, ValueError):
        i = 0
    return faixa[i % len(faixa)]


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
    fator_m = acabamentos.get("fator_m") or 1.0
    largura = LARGURA_M / fator_m
    codigos = {t: sorted({a["codigos"][t] for a in ambientes if t in a["codigos"]}) for t in CORES}
    n = 0
    for a in ambientes:
        for tipo, cod in sorted(a["codigos"].items()):
            if tipo not in CORES:
                continue
            material = catalogo.get(tipo, {}).get(cod, "")
            nome = _nome_camada(tipo, cod, material, a.get("contorno_origem") == "proposta")
            if nome not in doc.layers:
                camada = doc.layers.add(nome, color=_cor(tipo, cod, codigos))
                camada.description = _texto_seguro(material)
            atrib = {"layer": nome, "const_width": largura}
            if tipo == "parede":
                # só os trechos colados à parede; sem trecho identificado, o contorno inteiro
                trechos = [t for t in (a.get("trechos_parede") or []) if len(t) >= 2] or [a["contorno"]]
                for t in trechos:
                    msp.add_lwpolyline([tuple(p) for p in t], close=False, dxfattribs=atrib)
                    n += 1
                continue
            pts = [tuple(p) for p in a["contorno"]]
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts = pts[:-1]
            msp.add_lwpolyline(pts, close=True, dxfattribs=atrib)
            n += 1
    doc.audit()
    doc.saveas(saida)
    return n
