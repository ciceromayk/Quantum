"""Detecção dos contornos dos ambientes a partir da geometria da planta (sem zonas).

Passos:
1. Barreiras: linhas das camadas de parede (inclusive dentro de blocos) e esquadrias. Cada
   bloco de esquadria vira um retângulo que fecha o vão (só a parte dentro da parede, sem a
   folha), e o arco de abertura da porta ganha os dois raios (folha fechada).
2. Espaços livres: as barreiras engrossadas pela tolerância (une linhas duplas e pequenas
   folgas); cada "buraco" é um ambiente candidato, devolvido à face da parede.
3. Rótulo ↔ polígono: só casa quando a área do polígono bate com a área declarada no rótulo
   (tolerância), preferindo o polígono que contém o rótulo; rótulos fora do ambiente (com
   seta) casam com um vizinho até `raio_m`.
4. Ambientes integrados: o polígono é dividido pelas linhas de divisão (ex.: projeções) e
   pedaços são combinados até bater com as áreas declaradas.
5. O que sobra com dois rótulos num mesmo polígono recebe uma DIVISA PROPOSTA (reta que
   reparte a área na proporção declarada), marcada para conferência.

Nada é aceito sem bater com a área declarada; o resto vira pendência.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

try:
    from shapely.geometry import LineString, Point, Polygon
    from shapely import union_all
    from shapely.ops import polygonize, unary_union

    TEM_SHAPELY = True
except ImportError:  # pragma: no cover
    TEM_SHAPELY = False

from ezdxf import path as ezpath

PADRAO = {
    "camadas_parede": ["ALVENARIA", "DRY WALL", "REBOCO", "PILAR", "CERCADURA"],
    "camadas_esquadria": ["ESQ"],
    "camadas_divisao": ["PROJ"],
    "tolerancia_m": 0.02,
    "raio_m": 3.0,
    "max_pecas": 12,
}


@dataclass
class Contorno:
    pontos: list[tuple[float, float]]
    area: float  # unidades do desenho²
    origem: str  # "paredes", "divisao", "proposta" ou "grupo"
    erro: float  # diferença relativa para a área declarada
    perimetro_parede: float = 0.0  # unidades do desenho; sem os trechos abertos (divisas sem parede)


def _linha(e) -> LineString | None:
    try:
        pts = [(v.x, v.y) for v in ezpath.make_path(e).flattening(0.01)]
    except Exception:
        return None
    return LineString(pts) if len(pts) > 1 else None


def _estender(l: LineString, d: float) -> LineString:
    c = list(l.coords)

    def ext(a, b):
        dx, dy = a[0] - b[0], a[1] - b[1]
        n = math.hypot(dx, dy) or 1.0
        return (a[0] + dx / n * d, a[1] + dy / n * d)

    return LineString([ext(c[0], c[1])] + c[1:-1] + [ext(c[-1], c[-2])])


def _coletar(msp, cfg) -> tuple[list, list, list]:
    paredes, esq, div = set(cfg["camadas_parede"]), set(cfg["camadas_esquadria"]), set(cfg["camadas_divisao"])
    linhas, vaos, divisao = [], [], []
    for e in msp:
        t = e.dxftype()
        camada = e.dxf.get("layer", "0")
        if t == "INSERT":
            try:
                vs = list(e.virtual_entities())
            except Exception:
                continue
            if camada in esq:
                g = [_linha(v) for v in vs if v.dxf.get("layer") in paredes and v.dxftype() != "WIPEOUT"]
                g = [x for x in g if x is not None]
                if g:
                    r = unary_union(g).minimum_rotated_rectangle
                    if r.area > 0:
                        vaos.append(r)
                for v in vs:
                    if v.dxftype() == "ARC":
                        c = (v.dxf.center.x, v.dxf.center.y)
                        for p in (v.start_point, v.end_point):
                            linhas.append(LineString([c, (p.x, p.y)]))
            else:
                for v in vs:
                    cv = v.dxf.get("layer")
                    if v.dxftype() in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE"):
                        if cv in paredes and (g := _linha(v)) is not None:
                            linhas.append(g)
                        elif cv in div and (g := _linha(v)) is not None:
                            divisao.append(g)
        elif t in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE"):
            if camada in paredes or camada in esq:
                if (g := _linha(e)) is not None:
                    linhas.append(g)
            elif camada in div and (g := _linha(e)) is not None:
                divisao.append(g)
    return linhas, vaos, divisao


def _junto(peca: Polygon, espaco: Polygon, tol: float) -> float:
    """Comprimento do contorno da peça que corre sobre o contorno do espaço (paredes e vãos)."""
    return peca.exterior.intersection(espaco.exterior.buffer(tol * 1.5)).length


def _corte_reto(p: Polygon, ux: float, uy: float, alvo: float):
    """Corta p por uma reta perpendicular a (ux, uy) deixando a fração `alvo` da área no lado de baixo."""
    minx, miny, maxx, maxy = p.bounds
    L = math.hypot(maxx - minx, maxy - miny) * 2 + 1
    proj = [ux * x + uy * y for x, y in p.exterior.coords]
    lo, hi = min(proj), max(proj)

    def lado(t):
        cx, cy = ux * t, uy * t  # ponto da reta; o semiplano vai para -u
        return p.intersection(Polygon([
            (cx - uy * L, cy + ux * L), (cx + uy * L, cy - ux * L),
            (cx + uy * L - ux * L, cy - ux * L - uy * L), (cx - uy * L - ux * L, cy + ux * L - uy * L),
        ]))

    for _ in range(40):
        t = (lo + hi) / 2
        if lado(t).area / p.area < alvo:
            lo = t
        else:
            hi = t
    q1 = lado((lo + hi) / 2)
    return q1, p.difference(q1)


def _divisa_proposta(p: Polygon, a1, a2, pt1, pt2):
    """Reta que reparte a área na proporção a1:a2, deixando cada rótulo do seu lado.

    Tenta a direção entre os rótulos e as direções das paredes (eixos x e y); fica com a divisa
    mais curta em que os dois lados saem inteiros (um polígono só cada)."""
    dx, dy = pt2.x - pt1.x, pt2.y - pt1.y
    n = math.hypot(dx, dy)
    if n == 0:
        return None
    direcoes = [(dx / n, dy / n), (math.copysign(1, dx) if dx else 1, 0), (0, math.copysign(1, dy) if dy else 1)]
    melhor = None
    for ux, uy in direcoes:
        if ux * dx + uy * dy <= 0:  # rótulo 2 precisa estar à frente do 1 nessa direção
            continue
        q1, q2 = _corte_reto(p, ux, uy, a1 / (a1 + a2))
        if q1.geom_type != "Polygon" or q2.geom_type != "Polygon":
            continue
        if q1.distance(pt1) > q2.distance(pt1) or q2.distance(pt2) > q1.distance(pt2):
            continue
        divisa = q1.exterior.length + q2.exterior.length - p.exterior.length
        if melhor is None or divisa < melhor[0]:
            melhor = (divisa, q1, q2)
    return melhor[1:] if melhor else None


@dataclass
class GrupoIntegrado:
    rotulos: list[int]
    contorno: Contorno  # espaço inteiro; a área bate com a soma dos rótulos


def detectar(
    msp, rotulos: list[tuple[str, float, tuple[float, float]]], fator_m: float, config: dict | None = None
) -> tuple[dict[int, Contorno], list[GrupoIntegrado]]:
    """`rotulos`: (nome, área declarada em m², ponto do rótulo).

    Devolve {índice do rótulo: Contorno} e os grupos integrados (3 ou mais ambientes num mesmo
    espaço, sem linha que os separe) cuja área total confere, para o usuário dividir.
    """
    if not TEM_SHAPELY or not rotulos:
        return {}, []
    cfg = {**PADRAO, **(config or {})}
    tol = cfg["tolerancia_m"] / fator_m
    raio = cfg["raio_m"] / fator_m
    tol_area = cfg.get("tolerancia_area", 0.05)
    f2 = fator_m * fator_m

    linhas, vaos, divisao = _coletar(msp, cfg)
    if not linhas:
        return {}, []
    # grade de precisão: uniões robustas (sem "non-noded intersection") em qualquer versão do GEOS
    grade = tol / 20
    rede = union_all([l.buffer(tol, cap_style=2) for l in linhas] + vaos, grid_size=grade)
    buracos = [Polygon(i) for g in getattr(rede, "geoms", [rede]) for i in g.interiors]
    poligonos = [h.buffer(tol, join_style=2) for h in buracos if h.area * f2 > 0.3]
    poligonos = [p for p in poligonos if p.geom_type == "Polygon"]
    pts = [Point(*r[2]) for r in rotulos]

    def erro(area_desenho, a):
        return abs(area_desenho * f2 - a) / a

    # 3. rótulo ↔ polígono inteiro
    pares = []
    for i, (_, a, _) in enumerate(rotulos):
        for j, p in enumerate(poligonos):
            d = p.distance(pts[i])
            if d <= raio and (e := erro(p.area, a)) <= tol_area:
                pares.append((d > 0, e, d, i, j))
    out: dict[int, Contorno] = {}
    grupos: list[GrupoIntegrado] = []
    usados: set[int] = set()
    for _, e, _, i, j in sorted(pares):
        if i in out or j in usados:
            continue
        out[i] = Contorno(list(poligonos[j].exterior.coords), poligonos[j].area, "paredes", e, poligonos[j].exterior.length)
        usados.add(j)

    # 4. integrados: divide pelas linhas de divisão e combina pedaços
    ext = [_estender(l, 0.15 / fator_m) for l in divisao]
    # cada rótulo restante pertence a um só espaço: o que o contém, ou o mais próximo até 1 m
    livres = [j for j in range(len(poligonos)) if j not in usados]
    dono: dict[int, int] = {}
    for i in range(len(rotulos)):
        if i in out:
            continue
        perto = [(poligonos[j].distance(pts[i]), poligonos[j].area, j) for j in livres]
        perto = [c for c in perto if c[0] <= 1.0 / fator_m]
        if perto:
            dono[i] = min(perto)[2]
    for j, p in enumerate(poligonos):
        if j in usados:
            continue
        labs = [i for i, dj in dono.items() if dj == j]
        if not labs:
            continue
        cortes = [l.intersection(p) for l in ext if l.intersects(p)]
        pecas = []
        if cortes:
            pecas = [q for q in polygonize(union_all([p.exterior] + [c for c in cortes if not c.is_empty], grid_size=grade))
                     if q.area * f2 > 0.05 and p.buffer(tol).contains(q)]
        cand = []
        if len(pecas) >= 2:
            kmax = 3 if len(pecas) <= cfg["max_pecas"] else 2
            for k in range(1, kmax + 1):
                for comb in itertools.combinations(range(len(pecas)), k):
                    u = union_all([pecas[c] for c in comb], grid_size=grade)
                    if u.geom_type != "Polygon":
                        continue
                    for i in labs:
                        if (e := erro(u.area, rotulos[i][1])) <= tol_area:
                            cand.append((not u.buffer(tol).contains(pts[i]), e, u.distance(pts[i]), i, comb, u))
        tomadas: set[int] = set()
        for _, e, _, i, comb, u in sorted(cand, key=lambda c: c[:3]):
            if i in out or tomadas & set(comb):
                continue
            out[i] = Contorno(list(u.exterior.coords), u.area, "divisao", e, _junto(u, p, tol))
            tomadas |= set(comb)
        espaco = p
        if tomadas:
            usados.add(j)
            espaco = p.difference(union_all([pecas[c] for c in tomadas], grid_size=grade), grid_size=grade)
            if espaco.geom_type == "MultiPolygon":  # migalhas da grade
                espaco = max(espaco.geoms, key=lambda g: g.area)
            if espaco.geom_type != "Polygon" or espaco.is_empty:
                continue
        # 5. dois rótulos no mesmo espaço (ou no que sobrou dele): divisa proposta proporcional às áreas
        labs = [i for i in labs if i not in out]
        if len(labs) == 2:
            i1, i2 = labs
            a1, a2 = rotulos[i1][1], rotulos[i2][1]
            if erro(espaco.area, a1 + a2) <= tol_area:
                r = _divisa_proposta(espaco, a1, a2, pts[i1], pts[i2])
                if r:
                    q1, q2 = r
                    out[i1] = Contorno(list(q1.exterior.coords), q1.area, "proposta", erro(q1.area, a1), _junto(q1, p, tol))
                    out[i2] = Contorno(list(q2.exterior.coords), q2.area, "proposta", erro(q2.area, a2), _junto(q2, p, tol))
                    usados.add(j)
        elif len(labs) == 1 and tomadas:
            # o que sobrou depois das divisas é o último ambiente
            i = labs[0]
            if (e := erro(espaco.area, rotulos[i][1])) <= tol_area:
                out[i] = Contorno(list(espaco.exterior.coords), espaco.area, "divisao", e, _junto(espaco, p, tol))
        elif len(labs) >= 3:
            soma = sum(rotulos[i][1] for i in labs)
            if (e := erro(espaco.area, soma)) <= tol_area:
                grupos.append(GrupoIntegrado(labs, Contorno(list(espaco.exterior.coords), espaco.area, "grupo", e, _junto(espaco, p, tol))))
                usados.add(j)
    return out, grupos
