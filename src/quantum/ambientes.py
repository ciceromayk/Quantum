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
from dataclasses import dataclass, field

try:
    from shapely.geometry import LineString, Point, Polygon
    from shapely import STRtree
    from shapely import union_all
    from shapely.ops import nearest_points, polygonize, unary_union

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
    "reentrancia_prof_m": 0.15,  # profundidade máxima da reentrância de esquadria aplainada
    "reentrancia_vao_m": 3.0,    # largura máxima do vão aplainado
}


@dataclass
class Contorno:
    pontos: list[tuple[float, float]]
    area: float  # unidades do desenho²
    origem: str  # "paredes", "divisao", "proposta" ou "grupo"
    erro: float  # diferença relativa para a área declarada
    perimetro_parede: float = 0.0  # unidades do desenho; sem os trechos abertos (divisas sem parede)
    trechos_parede: list[list[tuple[float, float]]] = field(default_factory=list)
    """Partes do contorno que correm junto a uma parede, para o revestimento de parede.

    O contorno fechado mede piso e teto; a parede só existe onde há parede mesmo (uma divisa
    com o ambiente vizinho, proposta ou por linha de projeção, não é parede)."""


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


def _coletar(msp, cfg, tol: float) -> tuple[list, list, list]:
    paredes, esq, div = set(cfg["camadas_parede"]), set(cfg["camadas_esquadria"]), set(cfg["camadas_divisao"])
    linhas, vaos, divisao, raios = [], [], [], []
    for e in msp:
        t = e.dxftype()
        camada = e.dxf.get("layer", "0")
        if t == "INSERT":
            try:
                vs = list(e.virtual_entities())
            except Exception:
                continue
            if camada in esq:
                # o vão é fechado pelo retângulo das linhas de parede do bloco (as faces e os
                # batentes): a porta em si (folha, arco de abertura, alisares) não entra no desenho
                g = [_linha(v) for v in vs if v.dxf.get("layer") in paredes and v.dxftype() != "WIPEOUT"]
                g = [x for x in g if x is not None]
                r = unary_union(g).minimum_rotated_rectangle if g else None
                if r is not None and r.area > 0:
                    vaos.append(r)
                # o vão também pode ser fechado por um raio do arco de abertura, mas só o que
                # atravessa o vão: o outro é a folha aberta, dentro do ambiente. A escolha é
                # feita no fim, com todas as paredes na mão.
                for v in vs:
                    if v.dxftype() == "ARC":
                        c = (v.dxf.center.x, v.dxf.center.y)
                        for q in (v.start_point, v.end_point):
                            raios.append(LineString([c, (q.x, q.y)]))
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
    if raios and linhas:
        arvore = STRtree(linhas)
        for raio in raios:
            ponta = Point(raio.coords[-1])
            # a ponta solta da folha aberta não encosta em parede nenhuma; a do raio que
            # atravessa o vão encosta no outro lado, e só esse fecha o vão
            if any(linhas[k].distance(ponta) <= tol * 3 for k in arvore.query(ponta.buffer(tol * 3))):
                linhas.append(raio)
    return linhas, vaos, divisao


def _reto_no_anel(pts: list[tuple[float, float]], prof: float, vao: float, lado_min: float) -> list[tuple[float, float]]:
    """Anel sem as reentrâncias das esquadrias e com os cantos limpos.

    Os lados longos são as faces de parede. Entre dois deles, o que estiver no meio (batente,
    requadro, alisar, degrau da tolerância) é apagado quando não se afasta mais que `prof` das
    duas faces, num vão de até `vao`:
    - faces paralelas: a linha segue reta de uma à outra;
    - faces em ângulo: o canto vai para o encontro das duas faces, em esquadro.
    Um canto de verdade ou um recorte fundo se afasta mais que `prof` e continua no contorno."""
    n = len(pts)
    longos = [k for k in range(n) if math.dist(pts[k], pts[(k + 1) % n]) >= lado_min]
    if len(longos) < 3:
        return pts
    # começa no meio do lado mais longo (uma parede inteira): assim a emenda do anel cai numa
    # reta, e todo canto fica no meio do caminho, onde é limpo
    maior = max(longos, key=lambda k: math.dist(pts[k], pts[(k + 1) % n]))
    (x0, y0), (x1, y1) = pts[maior], pts[(maior + 1) % n]
    meio_lado = ((x0 + x1) / 2, (y0 + y1) / 2)
    pts = [meio_lado] + pts[(maior + 1) % n:] + pts[: (maior + 1) % n]
    n = len(pts)
    longo = [math.dist(pts[k], pts[(k + 1) % n]) >= lado_min for k in range(n)]

    def dir_(k):
        (x0, y0), (x1, y1) = pts[k], pts[(k + 1) % n]
        d = math.hypot(x1 - x0, y1 - y0) or 1.0
        return (x1 - x0) / d, (y1 - y0) / d

    def fora(k, m):  # distância do ponto m à reta do lado k
        ux, uy = dir_(k)
        dx, dy = pts[m][0] - pts[k][0], pts[m][1] - pts[k][1]
        return abs(-uy * dx + ux * dy)

    def encontro(k, b):
        """Ponto onde as retas dos lados k e b se cruzam (None se são paralelas)."""
        ux, uy = dir_(k)
        vx, vy = dir_(b)
        det = ux * vy - uy * vx
        if abs(det) < 1e-9:
            return None
        (x0, y0), (x1, y1) = pts[k], pts[b]
        t = ((x1 - x0) * vy - (y1 - y0) * vx) / det
        return (x0 + ux * t, y0 + uy * t)

    saida = [pts[0]]
    k = 0
    while k < n:
        if not longo[k]:
            saida.append(pts[(k + 1) % n])
            k += 1
            continue
        salto, canto = k, None
        for b in range(min(k + 10, n - 1), k, -1):
            if not longo[b] or math.dist(pts[(k + 1) % n], pts[b]) > vao:
                continue
            ux, uy = dir_(k)
            vx, vy = dir_(b)
            meio = range(k + 1, min(b + 2, n))
            if ux * vx + uy * vy >= math.cos(math.radians(10)):  # mesma face, dos dois lados
                # degrau de verdade (ponta de parede, viradinha): as duas faces são paralelas
                # mas não estão no mesmo plano, então a virada fica no contorno
                if max(fora(k, b), fora(k, (b + 1) % n)) > prof / 5:
                    continue
                if any(fora(k, m) > prof for m in meio):
                    continue
                salto, canto = b, None
                break
            p = encontro(k, b)  # faces em ângulo: o canto é o encontro delas
            if p is None or any(min(fora(k, m), fora(b, m)) > prof for m in meio):
                continue
            # só degrau de canto: o que está no meio tem que caber perto do canto ideal, senão
            # é um chanfro ou um recorte de verdade
            if any(math.dist(p, pts[m]) > prof * 2 for m in range(k + 1, min(b + 1, n))):
                continue
            salto, canto = b, p
            break
        if salto == k:  # nada a juntar: o lado segue como está
            saida.append(pts[(k + 1) % n])
            k += 1
            continue
        if canto is not None:
            saida.append(canto)
        # continua a partir do lado b, que ainda pode ser o começo da próxima junção (o canto
        # seguinte da mesma parede)
        k = salto
    if len(saida) > 1 and saida[0] == saida[-1]:
        saida = saida[:-1]
    saida = _sem_colineares(saida)
    return saida if len(saida) >= 3 else pts


def _sem_colineares(pts: list[tuple[float, float]], tol: float = 1e-6) -> list[tuple[float, float]]:
    """Tira vértices que ficaram no meio de uma reta (inclusive o ponto de emenda do anel)."""
    n = len(pts)
    if n < 4:
        return pts
    fora = []
    for i in range(n):
        a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        area2 = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        base = math.dist(a, c) or 1.0
        if area2 / base > tol:
            fora.append(b)
    return fora if len(fora) >= 3 else pts


def _retificar(p: Polygon, prof: float, vao: float = 3.0, lado_min: float = 0.25) -> Polygon:
    """Contorno sem os batentes de porta e requadros de janela, reto na face da parede."""
    try:
        base = p.simplify(prof / 10)
        if base.geom_type != "Polygon" or base.is_empty:
            base = p
        anel = list(base.exterior.coords)
        anel = anel[:-1] if len(anel) > 1 and anel[0] == anel[-1] else anel
        if len(anel) < 5:
            return p
        # cada passada junta lados que a anterior deixou longos o bastante; entre elas o anel é
        # girado, porque o ponto onde ele começa e termina não é limpo na passada
        for giro in (0, 2, 3):
            if giro:
                corte = len(anel) // giro
                anel = anel[corte:] + anel[:corte]
            anel = _reto_no_anel(anel, prof, vao, lado_min)
        q = Polygon(anel)
        if not q.is_valid:
            q = q.buffer(0)
    except Exception:
        return p
    if q.geom_type == "MultiPolygon":
        q = max(q.geoms, key=lambda g: g.area)
    return q if q.geom_type == "Polygon" and not q.is_empty else p


def _junto_da_parede(a, b, borda, original, limite: float, folga: float) -> bool:
    """O pedaço a→b corre junto a uma parede?

    Perto do contorno do espaço livre (a folga é o quanto a retificação pode ter afastado a
    linha) e com a peça original também junto à parede ali — se ela está longe, aquilo é divisa
    com o vizinho (linha de projeção ou divisa proposta), que não é parede."""
    for t in (0.2, 0.5, 0.8):
        p = Point(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        if borda.distance(p) > limite:
            return False
        if borda.distance(nearest_points(original, p)[0]) > folga:
            return False
    return True


def _contorno(peca: Polygon, espaco: Polygon | None, tol: float, prof: float, vao: float, origem: str, erro: float,
              grade: float = 0.0) -> Contorno:
    """Contorno desenhado e medido: reto nas esquadrias, com os trechos de parede separados.

    `espaco` é o espaço livre inteiro de onde a peça saiu: o que coincide com o contorno dele é
    parede (ou vão fechado por esquadria); o resto é divisa com o ambiente vizinho e não conta
    no revestimento de parede.

    A separação é feita por distância, pedaço a pedaço (passo de ~5 cm), e não por sobreposição
    de geometrias: um `buffer` do contorno do espaço faz o GEOS 3.12 do Pyodide abortar o
    processo inteiro ("depth mismatch"), que não é um erro que se possa tratar em Python."""
    reto = _retificar(peca, prof, vao)
    anel = list(reto.exterior.coords)
    if espaco is None:
        trechos = [anel]
    else:
        borda = espaco.exterior
        passo = max(prof / 3, 1e-9)
        trechos, atual = [], []
        for i in range(len(anel) - 1):
            a, b = anel[i], anel[i + 1]
            n = max(1, math.ceil(math.dist(a, b) / passo))
            for k in range(n):
                p0 = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                p1 = (a[0] + (b[0] - a[0]) * (k + 1) / n, a[1] + (b[1] - a[1]) * (k + 1) / n)
                if _junto_da_parede(p0, p1, borda, peca.exterior, prof + tol, tol * 1.5):
                    if not atual:
                        atual = [p0]
                    atual.append(p1)
                elif atual:
                    trechos.append(atual)
                    atual = []
        if atual:
            trechos.append(atual)
        # a emenda do anel fica no meio de uma parede: junta o último trecho ao primeiro
        if len(trechos) > 1 and trechos[0][0] == anel[0] and trechos[-1][-1] == anel[-1]:
            trechos[0] = trechos.pop()[:-1] + trechos[0]
        trechos = [list(LineString(t).simplify(tol / 10).coords) for t in trechos if len(t) > 1]
    perimetro = sum(LineString(t).length for t in trechos)
    return Contorno(anel, reto.area, origem, erro, perimetro, trechos)


def _corte_reto(p: Polygon, ux: float, uy: float, alvo: float, grade: float = 0.0):
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
        ]), grid_size=grade)

    for _ in range(40):
        t = (lo + hi) / 2
        if lado(t).area / p.area < alvo:
            lo = t
        else:
            hi = t
    q1 = lado((lo + hi) / 2)
    return q1, p.difference(q1, grid_size=grade)


def _divisa_proposta(p: Polygon, a1, a2, pt1, pt2, grade: float = 0.0):
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
        q1, q2 = _corte_reto(p, ux, uy, a1 / (a1 + a2), grade)
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

    linhas, vaos, divisao = _coletar(msp, cfg, tol)
    if not linhas:
        return {}, []
    # grade de precisão: uniões robustas (sem "non-noded intersection") em qualquer versão do GEOS
    grade = tol / 20
    rede = union_all([l.buffer(tol, cap_style=2) for l in linhas] + vaos, grid_size=grade)
    buracos = [Polygon(i) for g in getattr(rede, "geoms", [rede]) for i in g.interiors]
    poligonos = [h.buffer(tol, join_style=2) for h in buracos if h.area * f2 > 0.3]
    poligonos = [p for p in poligonos if p.geom_type == "Polygon"]
    prof, vao = cfg["reentrancia_prof_m"] / fator_m, cfg["reentrancia_vao_m"] / fator_m

    def montar(peca, origem, e, espaco=None):
        """Contorno pronto: linha reta nas esquadrias e trechos de parede separados.

        O casamento com o rótulo usa a peça como ela saiu da planta; a retificação vem depois,
        só no que é desenhado e medido."""
        return _contorno(peca, espaco, tol, prof, vao, origem, e, grade)
    pts = [Point(*r[2]) for r in rotulos]

    def erro(area_desenho, a):
        return abs(area_desenho * f2 - a) / a

    # 3. rótulo ↔ polígono inteiro
    dentro = {j: {i for i in range(len(rotulos)) if p.distance(pts[i]) == 0} for j, p in enumerate(poligonos)}
    pares = []
    for i, (_, a, _) in enumerate(rotulos):
        for j, p in enumerate(poligonos):
            d = p.distance(pts[i])
            # espaço que já tem rótulo dentro é dos rótulos de dentro: um rótulo de fora (com
            # seta) só pode casar com espaço sem dono, senão toma o ambiente do vizinho
            if d > 0 and dentro[j] and i not in dentro[j]:
                continue
            if d <= raio and (e := erro(p.area, a)) <= tol_area:
                pares.append((d > 0, e, d, i, j))
    out: dict[int, Contorno] = {}
    grupos: list[GrupoIntegrado] = []
    usados: set[int] = set()
    for _, e, _, i, j in sorted(pares):
        if i in out or j in usados:
            continue
        out[i] = montar(poligonos[j], "paredes", e)
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
        cortes = [l.intersection(p, grid_size=grade) for l in ext if l.intersects(p)]
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
            out[i] = montar(u, "divisao", e, p)
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
            # antes de propor uma reta, tenta repartir os pedaços de projeção restantes entre os dois
            resto = [k for k in range(len(pecas)) if k not in tomadas]
            if 2 <= len(resto) <= cfg["max_pecas"] and erro(espaco.area, a1 + a2) <= tol_area:
                melhor = None
                for mask in range(1, 2 ** len(resto) - 1):
                    lado1 = [resto[b] for b in range(len(resto)) if mask >> b & 1]
                    lado2 = [k for k in resto if k not in lado1]
                    u1 = union_all([pecas[k] for k in lado1], grid_size=grade)
                    u2 = union_all([pecas[k] for k in lado2], grid_size=grade)
                    if u1.geom_type != "Polygon" or u2.geom_type != "Polygon":
                        continue
                    e1, e2 = erro(u1.area, a1), erro(u2.area, a2)
                    if e1 <= tol_area and e2 <= tol_area and u1.distance(pts[i1]) <= u2.distance(pts[i1]) \
                            and u2.distance(pts[i2]) <= u1.distance(pts[i2]) and (melhor is None or e1 + e2 < melhor[0]):
                        melhor = (e1 + e2, u1, u2, e1, e2)
                if melhor:
                    _, u1, u2, e1, e2 = melhor
                    out[i1] = montar(u1, "divisao", e1, p)
                    out[i2] = montar(u2, "divisao", e2, p)
                    usados.add(j)
                    continue
            if erro(espaco.area, a1 + a2) <= tol_area:
                r = _divisa_proposta(espaco, a1, a2, pts[i1], pts[i2], grade)
                if r:
                    q1, q2 = r
                    out[i1] = montar(q1, "proposta", erro(q1.area, a1), p)
                    out[i2] = montar(q2, "proposta", erro(q2.area, a2), p)
                    usados.add(j)
        elif len(labs) == 1 and tomadas:
            # o que sobrou depois das divisas é o último ambiente
            i = labs[0]
            if (e := erro(espaco.area, rotulos[i][1])) <= tol_area:
                out[i] = montar(espaco, "divisao", e, p)
        elif len(labs) >= 3:
            soma = sum(rotulos[i][1] for i in labs)
            if (e := erro(espaco.area, soma)) <= tol_area:
                grupos.append(GrupoIntegrado(labs, montar(espaco, "grupo", e, p)))
                usados.add(j)
    return out, grupos
