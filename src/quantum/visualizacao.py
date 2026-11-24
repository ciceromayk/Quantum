"""Geometria simplificada do Model para o visualizador do navegador.

Explode blocos (com as transformações), achata curvas em segmentos e agrupa por camada,
com a cor da camada. Hachuras (preenchimentos) ficam de fora para não poluir; textos vão
como ponto + conteúdo. Coordenadas em metros, arredondadas a 1 mm.
"""

from __future__ import annotations

from ezdxf import colors, disassemble
from ezdxf import path as ezpath

from .ingestao import limpar_texto

LINEARES = {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE", "SOLID", "TRACE", "3DFACE"}
MAX_PONTOS = 1_500_000  # acima disso o resto é cortado (avisado no resultado)


def _cor_camada(doc, nome: str) -> str:
    try:
        camada = doc.layers.get(nome)
        if camada.rgb:
            r, g, b = camada.rgb
        else:
            aci = abs(camada.color) or 7
            r, g, b = colors.aci2rgb(aci)
    except Exception:
        r, g, b = 255, 255, 255
    if r > 235 and g > 235 and b > 235:  # branco (ACI 7) vira preto no fundo claro
        r, g, b = 40, 40, 40
    return f"#{r:02x}{g:02x}{b:02x}"


def geometria(msp, fator_m: float) -> dict:
    doc = msp.doc
    f = fator_m or 1.0
    tol = 0.005 / f  # 5 mm de flecha nas curvas
    camadas: dict[str, dict] = {}
    textos: list[list] = []
    total = 0
    cortado = False
    minx = miny = float("inf")
    maxx = maxy = float("-inf")

    for e in disassemble.recursive_decompose(msp):
        t = e.dxftype()
        camada = e.dxf.get("layer", "0")
        if t in ("TEXT", "MTEXT"):
            try:
                txt = limpar_texto(e.plain_text() if t == "MTEXT" else e.dxf.text)
                p = e.dxf.insert
                h = e.dxf.get("char_height" if t == "MTEXT" else "height", 0.1) or 0.1
            except Exception:
                continue
            if txt:
                textos.append([round(p.x * f, 3), round(p.y * f, 3), round(h * f, 3), txt[:80], camada])
            continue
        if t not in LINEARES:
            continue
        if total >= MAX_PONTOS:
            cortado = True
            break
        try:
            pts = [(v.x * f, v.y * f) for v in ezpath.make_path(e).flattening(tol)]
        except Exception:
            continue
        if len(pts) < 2:
            continue
        plano = []
        for x, y in pts:
            plano += [round(x, 3), round(y, 3)]
            minx, maxx = min(minx, x), max(maxx, x)
            miny, maxy = min(miny, y), max(maxy, y)
        total += len(pts)
        c = camadas.get(camada)
        if c is None:
            c = camadas[camada] = {"cor": _cor_camada(doc, camada), "linhas": []}
        c["linhas"].append(plano)

    caixa = [round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3)] if total else None
    return {"caixa": caixa, "foco": _foco(camadas) or caixa, "camadas": camadas, "textos": textos, "pontos": total, "cortado": cortado}


def _foco(camadas: dict) -> list[float] | None:
    """Caixa do miolo do desenho (descarta 1% dos pontos em cada ponta), para enquadrar sem
    que elementos soltos e distantes (quadros, legendas) deixem a planta pequena."""
    xs, ys = [], []
    for c in camadas.values():
        for l in c["linhas"]:
            xs += l[0::2]
            ys += l[1::2]
    if len(xs) < 50:
        return None
    xs.sort()
    ys.sort()
    k = len(xs) // 100
    return [xs[k], ys[k], xs[-1 - k], ys[-1 - k]]
