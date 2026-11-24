"""Gera um DXF NOVO com polilinhas fechadas por acabamento. O arquivo original não é alterado.

O arquivo é montado do zero (ezdxf.new, AutoCAD 2013) e recebe uma cópia do Model do desenho
original pelo Importer do ezdxf: só entidades, blocos, camadas, tipos de linha e estilos usados.
Assim não herda objetos estranhos do arquivo de origem (por exemplo, um DXF convertido de DWG
pelo LibreDWG, que o AutoCAD recusa abrir). Entidades que o Importer não sabe copiar ficam de
fora (o contorno e a planta de referência continuam lá).

Para cada ambiente com contorno e etiqueta:
- piso e teto (QTD-PISO-<código>, QTD-TETO-<código>): uma LWPOLYLINE fechada, que é a área.
  Ambientes integrados (contornos que se encostam, sem parede entre eles) com o mesmo código
  viram uma polilinha só, sem a divisa: a área é contínua, embora o quantitativo continue
  somando ambiente por ambiente;
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

try:
    from shapely import union_all
    from shapely.geometry import Polygon

    TEM_SHAPELY = True
except ImportError:  # pragma: no cover
    TEM_SHAPELY = False

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
FRESTA_M = 0.02  # fresta máxima fechada ao unir integrados; menor que a ponta de parede mais fina


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


def _unir_integrados(ambientes: list[dict], tipo: str, folga: float, fator: float = 1.0) -> dict[str, list[tuple[list, bool]]]:
    """Peças a desenhar por código: contornos encostados com o mesmo acabamento viram uma só.

    Dois ambientes só se encostam quando não há parede entre eles (são integrados, separados
    por linha de projeção ou por divisa proposta); com o mesmo piso ou forro, a área é uma só.
    Devolve {código: [(anel, veio de divisa proposta)]}."""
    por_codigo: dict[str, list[dict]] = {}
    for a in ambientes:
        cod = a["codigos"].get(tipo)
        if cod:
            por_codigo.setdefault(cod, []).append(a)
    saida: dict[str, list[tuple[list, bool]]] = {}
    for cod, grupo in por_codigo.items():
        simples = [(a["contorno"], a.get("contorno_origem") == "proposta") for a in grupo]
        if not TEM_SHAPELY or len(grupo) < 2:
            saida[cod] = simples
            continue
        try:
            pols = [Polygon(a["contorno"]).buffer(0) for a in grupo]
            canto = {"join_style": 2, "mitre_limit": 5}  # canto em esquadro: o arredondado criaria vértices
            pecas = []
            for i, p in enumerate(pols):
                if p.is_empty:
                    continue
                for peca in pecas:
                    if any(pols[k].distance(p) <= folga for k in peca):
                        peca.append(i)
                        break
                else:
                    pecas.append([i])
            # junta peças que passaram a se tocar pelo caminho (A-B e B-C viraram A-B-C)
            mudou = True
            while mudou:
                mudou = False
                for x in range(len(pecas)):
                    for y in range(x + 1, len(pecas)):
                        if any(pols[i].distance(pols[j]) <= folga for i in pecas[x] for j in pecas[y]):
                            pecas[x] += pecas.pop(y)
                            mudou = True
                            break
                    if mudou:
                        break
            juntas: list[tuple[list, bool]] = []
            for peca in pecas:
                if len(peca) == 1:
                    juntas.append(simples[peca[0]])
                    continue
                # fecha a fresta: a divisa proposta é reta e a parede vizinha nem sempre, então
                # entre as duas peças sobra uma cunha de poucos centímetros, que é piso também.
                costura = FRESTA_M / fator
                u = union_all([pols[i].buffer(costura, **canto) for i in peca]).buffer(-costura, **canto)
                u = u.simplify(folga)
                partes = [g for g in getattr(u, "geoms", [u]) if g.geom_type == "Polygon" and not g.is_empty]
                if not partes:
                    juntas += [simples[i] for i in peca]
                    continue
                # a divisa some: o contorno unido não é mais uma proposta
                juntas += [(list(g.exterior.coords), False) for g in partes]
            saida[cod] = juntas
        except Exception:
            saida[cod] = simples
    return saida


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

    def camada_de(tipo: str, cod: str, proposta: bool) -> dict:
        material = catalogo.get(tipo, {}).get(cod, "")
        nome = _nome_camada(tipo, cod, material, proposta)
        if nome not in doc.layers:
            camada = doc.layers.add(nome, color=_cor(tipo, cod, codigos))
            camada.description = _texto_seguro(material)
        return {"layer": nome, "const_width": largura}

    # parede: um trecho por pedaço colado à parede, ambiente por ambiente
    for a in ambientes:
        cod = a["codigos"].get("parede")
        if not cod:
            continue
        atrib = camada_de("parede", cod, a.get("contorno_origem") == "proposta")
        trechos = [t for t in (a.get("trechos_parede") or []) if len(t) >= 2] or [a["contorno"]]
        for t in trechos:
            msp.add_lwpolyline([tuple(p) for p in t], close=False, dxfattribs=atrib)
            n += 1

    # piso e teto: área fechada, com os integrados de mesmo acabamento unidos
    folga = (LARGURA_M / 2) / fator_m
    for tipo in ("piso", "teto"):
        for cod, pecas in sorted(_unir_integrados(ambientes, tipo, folga, fator_m).items()):
            for anel, proposta in pecas:
                pts = [tuple(p) for p in anel]
                if len(pts) > 1 and pts[0] == pts[-1]:
                    pts = pts[:-1]
                if len(pts) < 3:
                    continue
                msp.add_lwpolyline(pts, close=True, dxfattribs=camada_de(tipo, cod, proposta))
                n += 1
    doc.audit()
    doc.saveas(saida)
    return n
