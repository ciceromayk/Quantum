"""Gera a PLANTA FALADA pré-classificada a partir da planta de arquitetura.

A planta falada é a arquitetura com uma polilinha no eixo de cada parede, numa camada por
sistema (`0_DRY_WALL_70mm_+ST+ST`, `0_TIJOLO CERAMICO_14CM`…). Ela é a entrada do agente de
paredes e painéis (`agentes/paineis.py`), que monta a planilha padrão.

O que é LIDO da arquitetura:
- material: camada da parede (ALVENARIA ou DRY WALL);
- eixo e espessura: medidos entre as linhas paralelas das faces.

O que é INFERIDO (e marcado para o usuário conferir no CAD):
- perfil do drywall pela espessura total (48 / 70 / steel frame 90);
- chapa de cada face pelo ambiente daquele lado (área molhada → RU, varanda/fachada → GR,
  demais → ST);
- tijolo ou bloco de concreto (bloco junto de escada/elevador);
- espessura fora das nominais vai para a camada `0_A_CLASSIFICAR`.

Cada parede inferida recebe um texto curto na camada `QUANTUM_INFERIDO` dizendo o que foi
suposto. O usuário corrige a camada no CAD, apaga as marcas e manda a planta de volta.
"""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from shapely.ops import voronoi_diagram
from shapely.geometry import LineString, MultiPoint, Point, Polygon
from shapely import set_precision, union_all
from shapely.ops import linemerge
from shapely.strtree import STRtree

from .agentes.paineis import (CAMADAS_PADRAO, DIST_TEXTO_ALTURA_M, NAO_NOME, RX_ID_VAO, AgentePaineis, _chave,
                              _dist_ponto_polilinha, alturas_de_texto)
from .ingestao import abrir_documento, carregar

# especificação -> camada gravada (mesma grafia da planta falada do escritório)
CAMADA_DA_ESPEC = {
    "PERFIL 48MM + RU": "0_DRY_WALL_48MM_+RU",
    "PERFIL 70MM + RU + RU": "0_DRY_WALL_70MM_+RU+RU",
    "PERFIL 70MM + ST + RU": "0_DRY_WALL_70MM_+ST+RU",
    "PERFIL 70MM + ST + ST": "0_DRY_WALL_70mm_+ST+ST",
    "PERFIL STEEL FRAME 90MM + GR + GR": "0_STEEL_FRAME_90MM + GR + GR",
    "PERFIL STEEL FRAME 90MM + GR + RU": "0_STEEL_FRAME_90MM + GR + RU",
    "PERFIL STEEL FRAME 90MM + GR + ST": "0_STEEL_FRAME_90MM + GR + ST",
    "PERFIL STEEL FRAME 90MM + ST + RU": "0_STEEL_FRAME_90MM + ST + RU",
    "PERFIL STEEL FRAME 90MM + ST + ST": "0_STEEL_FRAME_90MM + ST + ST",
    "ALVENARIA TIJOLO DE 9CM": "0_TIJOLO CERÂMICO_9CM",
    "ALVENARIA TIJOLO DE 14CM": "0_TIJOLO CERAMICO_14CM",
    "ALVENARIA TIJOLO DE 19CM": "0_TIJOLO CERAMICO_19CM",
    "BLOCO DE CONCRETO DE 14CM": "0_BLOCO DE CONCRETO_14CM",
}
COR_DA_ESPEC = {  # cores ACI da planta falada padrão
    "PERFIL 70MM + ST + ST": 5, "PERFIL 70MM + ST + RU": 42, "PERFIL 70MM + RU + RU": 122, "PERFIL 48MM + RU": 3,
    "PERFIL STEEL FRAME 90MM + GR + ST": 60, "PERFIL STEEL FRAME 90MM + ST + RU": 230,
    "PERFIL STEEL FRAME 90MM + ST + ST": 6, "PERFIL STEEL FRAME 90MM + GR + GR": 200,
    "PERFIL STEEL FRAME 90MM + GR + RU": 150, "ALVENARIA TIJOLO DE 14CM": 1, "BLOCO DE CONCRETO DE 14CM": 4,
    "ALVENARIA TIJOLO DE 9CM": 30, "ALVENARIA TIJOLO DE 19CM": 2,
}
CAMADA_A_CLASSIFICAR = "0_A_CLASSIFICAR"
CAMADA_INFERIDO = "QUANTUM_INFERIDO"
CAMADA_LEGENDA = "QUADRO DE ALVENARIAS"

GRADE = 0.001  # m: grade de precisão das operações de geometria

PADRAO = {
    "camadas_alvenaria": ["ALVENARIA"],
    "camadas_drywall": ["DRY WALL", "DRYWALL", "DRY-WALL", "GESSO ACARTONADO"],
    "espessura_min_m": 0.04,
    "espessura_max_m": 0.30,
    "comprimento_min_m": 0.20,  # trecho de eixo menor que isso é ruído de encontro
}
RX_MOLHADA = re.compile(r"\b(BWC|WC|BANH|LAVABO|LAV|COZ|COZINHA|SERV|A S|AREA DE SERV|DML|COPA|GOURMET|CHURRAS)")
RX_EXTERNA = re.compile(r"\b(VARANDA|SACADA|TERRACO|TERRAÇO|FACHADA|EXTERN|JARDIM|PERGOLAD)")
RX_ESCADA = re.compile(r"\b(ESCADA|ELEV|ANTE ?CAMARA|ANTECAMARA|CAMARA)")


@dataclass
class Parede:
    pontos: list[tuple[float, float]]  # em metros
    material: str  # "alvenaria" ou "drywall"
    espessura_m: float
    nucleo_m: float | None = None
    especificacao: str | None = None
    lados: tuple[str, str] = ("", "")
    inferido: list[str] = field(default_factory=list)
    altura_texto: float | None = None  # parede baixa: altura escrita no desenho (MURETA h=0,20m)
    texto_altura: str = ""

    @property
    def comprimento_m(self) -> float:
        return sum(math.dist(a, b) for a, b in zip(self.pontos, self.pontos[1:]))


# ---------------------------------------------------------------------- leitura das faces
def _segmentos(msp, camadas: set[str], f: float) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Segmentos retos das faces das paredes, em metros (inclui blocos explodidos)."""
    out = []

    def add(e):
        if e.dxf.get("layer") not in camadas:
            return
        t = e.dxftype()
        if t == "LINE":
            pts = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
        elif t == "LWPOLYLINE":
            pts = [(x, y) for x, y in e.get_points("xy")]
            if e.closed and pts:
                pts.append(pts[0])
        elif t == "POLYLINE":
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            if e.is_closed and pts:
                pts.append(pts[0])
        else:
            return
        for a, b in zip(pts, pts[1:]):
            a, b = (a[0] * f, a[1] * f), (b[0] * f, b[1] * f)
            if math.dist(a, b) > 0.02:
                out.append((a, b))

    for e in msp:
        if e.dxftype() == "INSERT":
            try:
                for v in e.virtual_entities():
                    add(v)
            except Exception:
                continue
        else:
            add(e)
    return out


def _regiao(segs, emin: float, emax: float):
    """Faixa sólida da parede: o quadrilátero entre cada face e a face paralela mais próxima
    de cada lado. Camadas internas (perfil, chapa) só subdividem a mesma faixa."""
    if not segs:
        return None
    geo = [LineString(s) for s in segs]
    arvore = STRtree(geo)
    quads = []
    for i, (a, b) in enumerate(segs):
        L = math.dist(a, b)
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = -uy, ux
        melhor = {1: None, -1: None}
        for j in arvore.query(geo[i].buffer(emax + 0.01)):
            if j == i:
                continue
            c, e = segs[j]
            L2 = math.dist(c, e)
            if abs(ux * (e[1] - c[1]) / L2 - uy * (e[0] - c[0]) / L2) > 0.035:  # ~2°
                continue
            dd = (c[0] - a[0]) * nx + (c[1] - a[1]) * ny
            if not 0.004 <= abs(dd) <= emax:
                continue
            t1 = (c[0] - a[0]) * ux + (c[1] - a[1]) * uy
            t2 = (e[0] - a[0]) * ux + (e[1] - a[1]) * uy
            lo, hi = max(0.0, min(t1, t2)), min(L, max(t1, t2))
            if hi - lo < 0.03:
                continue
            lado = 1 if dd > 0 else -1
            if melhor[lado] is None or abs(dd) < abs(melhor[lado][0]):
                melhor[lado] = (dd, lo, hi)
        for v in melhor.values():
            if v is None:
                continue
            dd, lo, hi = v
            p1 = (a[0] + ux * lo, a[1] + uy * lo)
            p2 = (a[0] + ux * hi, a[1] + uy * hi)
            quads.append(Polygon([p1, p2, (p2[0] + nx * dd, p2[1] + ny * dd), (p1[0] + nx * dd, p1[1] + ny * dd)]))
    if not quads:
        return None
    # grade de precisão em toda união/buffer: o GEOS do Pyodide aborta o processo num
    # "non-noded intersection" (ver CLAUDE.md e PR #19)
    r = union_all([set_precision(q.buffer(0.003, join_style=2), GRADE) for q in quads], grid_size=GRADE)
    r = set_precision(r.buffer(-0.002, join_style=2), GRADE)
    # sobra de faixa mais fina que a parede mais fina (ex.: só a chapa) não é parede
    r = set_precision(r.buffer(-emin / 2.2, join_style=2), GRADE)
    return set_precision(r.buffer(emin / 2.2, join_style=2), GRADE)


def _juntar(linhas) -> list[LineString]:
    if not linhas:
        return []
    u = union_all(linhas, grid_size=GRADE)
    if u.geom_type == "LineString":
        return [u]
    m = linemerge(u) if u.geom_type == "MultiLineString" else u
    return [g for g in getattr(m, "geoms", [m]) if g.geom_type == "LineString"]


def _eixos(regiao, emin: float, emax: float, comp_min: float) -> list[tuple[list[tuple[float, float]], float]]:
    """Eixo de cada faixa (eixo medial aproximado pelo diagrama de Voronoi da borda)."""
    out = []
    for pg in getattr(regiao, "geoms", [regiao]):
        if pg.is_empty or pg.area < emin * comp_min:
            continue
        borda = pg.boundary.segmentize(0.03)
        pts = MultiPoint([c for ln in getattr(borda, "geoms", [borda]) for c in ln.coords])
        vor = voronoi_diagram(pts, edges=True)
        miolo = set_precision(pg.buffer(-emin * 0.3), GRADE)
        def planas(g):
            for x in getattr(g, "geoms", [g]):
                if x.geom_type == "LineString":
                    yield x
                else:
                    yield from planas(x)

        arestas = [e for e in planas(vor) if not e.is_empty and e.within(miolo)]
        if not arestas:
            continue
        linhas = _juntar(arestas)
        # galhos que morrem num canto (Voronoi solta um galho em cada quina): poda o que é curto
        # e tem uma ponta solta, até estabilizar
        for _ in range(4):
            pontas: dict[tuple[float, float], int] = {}
            for l in linhas:
                for c in (l.coords[0], l.coords[-1]):
                    k = (round(c[0], 3), round(c[1], 3))
                    pontas[k] = pontas.get(k, 0) + 1
            novas = []
            for l in linhas:
                c0, c1 = l.coords[0], l.coords[-1]
                solta = pontas[(round(c0[0], 3), round(c0[1], 3))] == 1 or pontas[(round(c1[0], 3), round(c1[1], 3))] == 1
                if solta and l.length < max(emax, 0.25) and len(linhas) > 1:
                    continue
                novas.append(l)
            if len(novas) == len(linhas):
                break
            linhas = _juntar(novas)
        for l in linhas:
            s = l.simplify(0.02)
            if s.length < comp_min:
                continue
            esp = [2 * pg.boundary.distance(s.interpolate(t, normalized=True)) for t in (0.2, 0.35, 0.5, 0.65, 0.8)]
            out.append(([(x, y) for x, y in s.coords], statistics.median(esp)))
    return out


# ---------------------------------------------------------------------- classificação
NUCLEOS = {"drywall": (0.048, 0.07, 0.09), "alvenaria": (0.09, 0.14, 0.19)}


def _nucleo(material: str, pontos, segs, arvore, emax: float) -> float | None:
    """Espessura do núcleo (perfil ou bloco), sem chapa nem reboco: a distância entre duas faces
    paralelas, cruzando a parede, que bate com uma espessura nominal."""
    l = LineString(pontos)
    votos: dict[float, int] = {}
    for t in (0.15, 0.3, 0.5, 0.7, 0.85):
        a = l.interpolate(max(0.0, t * l.length - 0.02))
        b = l.interpolate(min(l.length, t * l.length + 0.02))
        ux, uy = b.x - a.x, b.y - a.y
        n = math.hypot(ux, uy)
        if n == 0:
            continue
        ux, uy = ux / n, uy / n
        c = l.interpolate(t, normalized=True)
        r = emax / 2 + 0.02
        sonda = LineString([(c.x - uy * r, c.y + ux * r), (c.x + uy * r, c.y - ux * r)])
        offs = []
        for k in arvore.query(sonda):
            (p1, p2) = segs[k]
            L = math.dist(p1, p2)
            if abs(ux * (p2[1] - p1[1]) / L - uy * (p2[0] - p1[0]) / L) > 0.035:
                continue
            # cruzamento sonda × face pela conta (sem overlay do GEOS)
            q0, q1 = sonda.coords[0], sonda.coords[1]
            den = (q1[0] - q0[0]) * (p2[1] - p1[1]) - (q1[1] - q0[1]) * (p2[0] - p1[0])
            if abs(den) < 1e-12:
                continue
            ta = ((p1[0] - q0[0]) * (p2[1] - p1[1]) - (p1[1] - q0[1]) * (p2[0] - p1[0])) / den
            tb = ((p1[0] - q0[0]) * (q1[1] - q0[1]) - (p1[1] - q0[1]) * (q1[0] - q0[0])) / den
            if 0 <= ta <= 1 and 0 <= tb <= 1:
                x, y = q0[0] + ta * (q1[0] - q0[0]), q0[1] + ta * (q1[1] - q0[1])
                offs.append((x - c.x) * -uy + (y - c.y) * ux)
        achados = set()
        for i in range(len(offs)):
            for j in range(i + 1, len(offs)):
                dd = abs(offs[i] - offs[j])
                for nom in NUCLEOS[material]:
                    if abs(dd - nom) <= 0.004:
                        achados.add(nom)
        for nom in achados:
            votos[nom] = votos.get(nom, 0) + 1
    if not votos:
        return None
    melhor = max(votos.values())
    if melhor < 2:
        return None
    cands = [n for n, v in votos.items() if v == melhor]
    # drywall 70 com chapas (≈0,095) cai perto do núcleo 90: na dúvida, 70
    return min(cands) if material == "drywall" else max(cands)


def _perfil_drywall(e: float) -> str | None:
    if e < 0.04:
        return None
    if e <= 0.078:
        return "48"
    if e <= 0.106:
        return "70"
    if e <= 0.16:
        return "90"
    return None


def _tijolo(e: float) -> str | None:
    for nominal in (9, 14, 19):
        if abs(e - nominal / 100) <= 0.022:
            return str(nominal)
    return None


def _face(nome: str) -> str:
    k = _chave(nome)
    if not k:
        return "GR"  # sem ambiente do lado: face externa
    if RX_EXTERNA.search(k):
        return "GR"
    if RX_MOLHADA.search(k):
        return "RU"
    return "ST"


def classificar(p: Parede) -> None:
    a, b = p.lados
    if p.material == "drywall":
        perfil = {0.048: "48", 0.07: "70", 0.09: "90"}.get(p.nucleo_m) or _perfil_drywall(p.espessura_m)
        if perfil is None:
            p.inferido.append(f"espessura {p.espessura_m * 100:.1f} cm fora das nominais de drywall")
            return
        if perfil == "48":
            p.especificacao = "PERFIL 48MM + RU"
            p.inferido.append("shaft 48 mm com uma face RU")
            return
        fa, fb = _face(a), _face(b)
        if perfil == "70" and "GR" in (fa, fb):
            # drywall 70 não leva GR no padrão: face externa num drywall é RU (área técnica)
            fa, fb = ("RU" if fa == "GR" else fa), ("RU" if fb == "GR" else fb)
        ordem = ["GR", "ST", "RU"]
        c1, c2 = sorted((fa, fb), key=ordem.index)
        nome = f"PERFIL 70MM + {c1} + {c2}" if perfil == "70" else f"PERFIL STEEL FRAME 90MM + {c1} + {c2}"
        if nome not in CAMADA_DA_ESPEC:
            p.inferido.append(f"{nome} não existe no padrão")
            return
        p.especificacao = nome
        p.inferido.append(f"chapas {c1}/{c2} pelos ambientes: {a or 'externo'} | {b or 'externo'}")
    else:
        cm = str(round(p.nucleo_m * 100)) if p.nucleo_m else _tijolo(p.espessura_m)
        if cm is None:
            p.inferido.append(f"espessura {p.espessura_m * 100:.1f} cm fora das nominais de alvenaria")
            return
        if cm == "14" and (RX_ESCADA.search(_chave(a)) or RX_ESCADA.search(_chave(b))):
            p.especificacao = "BLOCO DE CONCRETO DE 14CM"
            p.inferido.append("bloco de concreto por estar junto de escada/elevador")
        else:
            p.especificacao = f"ALVENARIA TIJOLO DE {cm}CM"
            p.inferido.append(f"tijolo cerâmico (não bloco) de {cm} cm")


def _rotulos(d, f: float) -> list[tuple[str, tuple[float, float]]]:
    out = []
    for e in d.entidades:
        if e.area_rotulo is None or not e.ponto_texto:
            continue
        nome = (e.texto or "").strip()
        nome = re.sub(r"\s*\d+[.,]\d+\s*m[2²]?\s*$", "", nome, flags=re.I).strip()
        if nome:
            out.append((nome, (e.ponto_texto[0] * f, e.ponto_texto[1] * f)))
    if len(out) >= 3:
        return out
    # sem rótulo nome + área (planta exportada com textos soltos): usa os textos com cara de nome
    for e in d.entidades:
        if e.tipo not in ("TEXT", "MTEXT") or not e.texto or not e.insercao:
            continue
        t = _chave(e.texto)
        if len(t) < 3 or not re.search(r"[A-Z]{2}", t) or NAO_NOME.match(t) or RX_ID_VAO.match(t) or "=" in t:
            continue
        out.append((e.texto.strip(), (e.insercao[0] * f, e.insercao[1] * f)))
    return out


def _lado(ponto, rotulos, arvore_rot, paredes_uniao, raio: float = 6.0) -> str:
    """Ambiente do lado de uma face: o rótulo mais próximo que se enxerga dali sem atravessar
    outra parede."""
    if not rotulos:
        return ""
    p = Point(ponto)
    cand = sorted((math.dist(ponto, r[1]), k) for k in arvore_rot.query(p.buffer(raio)) for r in [rotulos[k]])
    for dist, k in cand[:8]:
        vista = LineString([ponto, rotulos[k][1]])
        if not vista.crosses(paredes_uniao) and not vista.within(paredes_uniao):
            return rotulos[k][0]
    return ""


# ---------------------------------------------------------------------- execução
def detectar_paredes(caminho: str | Path, config: dict | None = None, unidade: str | None = None,
                     desenho=None) -> tuple[list[Parede], dict]:
    """`desenho`: o Desenho já carregado (evita ler o arquivo de novo)."""
    cfg = {**PADRAO, **(config or {})}
    d = desenho if desenho is not None and getattr(desenho, "modelspace", None) is not None else carregar(caminho, unidade=unidade)
    f = d.fator_m or 1.0
    msp = d.modelspace
    emin, emax, cmin = cfg["espessura_min_m"], cfg["espessura_max_m"], cfg["comprimento_min_m"]
    paredes: list[Parede] = []
    regioes = []
    for material, chave in (("alvenaria", "camadas_alvenaria"), ("drywall", "camadas_drywall")):
        segs = _segmentos(msp, set(cfg[chave]), f)
        r = _regiao(segs, emin, emax)
        if r is None or r.is_empty:
            continue
        regioes.append(r)
        arv = STRtree([LineString(x) for x in segs])
        for pts, esp in _eixos(r, emin, emax, cmin):
            paredes.append(Parede(pts, material, esp, _nucleo(material, pts, segs, arv, emax)))
    uniao = union_all(regioes, grid_size=GRADE) if regioes else Polygon()
    rotulos = _rotulos(d, f)
    arvore = STRtree([Point(r[1]) for r in rotulos]) if rotulos else None
    for p in paredes:
        l = LineString(p.pontos)
        meio = l.interpolate(0.5, normalized=True)
        a, b = l.interpolate(max(0.0, l.length / 2 - 0.05)), l.interpolate(min(l.length, l.length / 2 + 0.05))
        ux, uy = b.x - a.x, b.y - a.y
        n = math.hypot(ux, uy) or 1.0
        nx, ny = -uy / n, ux / n
        off = p.espessura_m / 2 + 0.25
        pa, pb = (meio.x + nx * off, meio.y + ny * off), (meio.x - nx * off, meio.y - ny * off)
        p.lados = (_lado(pa, rotulos, arvore, uniao), _lado(pb, rotulos, arvore, uniao)) if arvore else ("", "")
        classificar(p)
    # parede baixa: texto MURETA/PEITORIL/GUARDA-CORPO com h= a até 1 m do eixo (mesma regra da planilha)
    baixas, _ = alturas_de_texto(AgentePaineis()._textos(msp))
    for h, t, x, y in baixas:
        cand = [(_dist_ponto_polilinha((x * f, y * f), p.pontos), k) for k, p in enumerate(paredes)]
        if cand and (m := min(cand))[0] <= DIST_TEXTO_ALTURA_M:
            paredes[m[1]].altura_texto, paredes[m[1]].texto_altura = h, re.sub(r"\s+", " ", t).strip()
    resumo = {"fator_m": f, "unidade": d.unidade, "rotulos": len(rotulos), "arquivo": str(caminho)}
    return paredes, resumo


def gravar(caminho_origem: str | Path, paredes: list[Parede], saida: str | Path, fator_m: float, doc=None) -> None:
    """Grava a planta falada: a arquitetura original + eixos nas camadas do padrão + marcas.
    `doc`: o documento já aberto (é alterado: use só depois da análise)."""
    doc = doc if doc is not None else abrir_documento(caminho_origem)
    msp = doc.modelspace()
    inv = 1.0 / (fator_m or 1.0)
    for esp, cam in CAMADA_DA_ESPEC.items():
        if cam not in doc.layers:
            doc.layers.add(cam, color=COR_DA_ESPEC.get(esp, 7))
    for cam, cor in ((CAMADA_A_CLASSIFICAR, 7), (CAMADA_INFERIDO, 8), (CAMADA_LEGENDA, 7)):
        if cam not in doc.layers:
            doc.layers.add(cam, color=cor)
    alt = 0.10 * inv
    for p in paredes:
        cam = CAMADA_DA_ESPEC[p.especificacao] if p.especificacao else CAMADA_A_CLASSIFICAR
        pts = [(x * inv, y * inv) for x, y in p.pontos]
        msp.add_lwpolyline(pts, dxfattribs={"layer": cam, "const_width": 0.03 * inv})
        if p.inferido or not p.especificacao or p.altura_texto is not None:
            l = LineString(pts)
            m = l.interpolate(0.5, normalized=True)
            partes = list(p.inferido) if p.inferido else ([] if p.especificacao else ["classificar"])
            if p.altura_texto is not None:
                partes.insert(0, f"parede baixa h={p.altura_texto:.2f} m (texto do desenho: {p.texto_altura})".replace(".", ",", 1))
            msg = "?" + "; ".join(partes)
            msp.add_text(msg[:120], dxfattribs={"layer": CAMADA_INFERIDO, "height": alt, "insert": (m.x, m.y)})
    # legenda fora do desenho (o leitor da planta falada ignora o que estiver dentro dela)
    xs = [x for p in paredes for x, _ in p.pontos] or [0.0]
    ys = [y for p in paredes for _, y in p.pontos] or [0.0]
    x0, y0 = (max(xs) + 3.0) * inv, max(ys) * inv
    linhas = [(e, CAMADA_DA_ESPEC[e]) for e in CAMADA_DA_ESPEC] + [("A CLASSIFICAR (espessura fora do padrão)", CAMADA_A_CLASSIFICAR)]
    passo = 0.45 * inv
    for k, (txt, cam) in enumerate(linhas):
        y = y0 - (k + 1) * passo
        msp.add_lwpolyline([(x0 + 0.2 * inv, y), (x0 + 1.2 * inv, y)], dxfattribs={"layer": cam, "const_width": 0.05 * inv})
        msp.add_text(txt, dxfattribs={"layer": CAMADA_LEGENDA, "height": 0.15 * inv, "insert": (x0 + 1.4 * inv, y - 0.05 * inv)})
    msp.add_text("LEGENDA - PLANTA FALADA (PRÉ-CLASSIFICADA PELO QUANTUM: CONFERIR)",
                 dxfattribs={"layer": CAMADA_LEGENDA, "height": 0.2 * inv, "insert": (x0, y0)})
    h = (len(linhas) + 1.5) * passo
    msp.add_lwpolyline([(x0 - 0.2 * inv, y0 + 0.4 * inv), (x0 + 9 * inv, y0 + 0.4 * inv), (x0 + 9 * inv, y0 - h),
                        (x0 - 0.2 * inv, y0 - h)], close=True, dxfattribs={"layer": CAMADA_LEGENDA})
    doc.saveas(saida)


def resumo_paredes(paredes: list[Parede]) -> list[dict]:
    tot: dict[str, dict] = {}
    for p in paredes:
        k = p.especificacao or "A CLASSIFICAR"
        r = tot.setdefault(k, {"especificacao": k, "comprimento_m": 0.0, "trechos": 0, "inferidos": 0})
        r["comprimento_m"] += p.comprimento_m
        r["trechos"] += 1
        r["inferidos"] += bool(p.inferido)
    ordem = [e for _, e in CAMADAS_PADRAO] + ["A CLASSIFICAR"]
    return sorted(({**r, "comprimento_m": round(r["comprimento_m"], 2)} for r in tot.values()), key=lambda r: ordem.index(r["especificacao"]))


def gerar(caminho: str | Path, saida: str | Path, config: dict | None = None, unidade: str | None = None,
          desenho=None, paredes_out: list | None = None) -> dict:
    """`paredes_out`: lista que recebe as paredes detectadas (para o visualizador)."""
    paredes, info = detectar_paredes(caminho, config, unidade, desenho)
    if paredes_out is not None:
        paredes_out.extend(paredes)
    msp = getattr(desenho, "modelspace", None)
    gravar(caminho, paredes, saida, info["fator_m"], msp.doc if msp is not None else None)
    baixas = [{"texto": p.texto_altura, "altura_m": p.altura_texto, "comprimento_m": round(p.comprimento_m, 2),
               "especificacao": p.especificacao or "A CLASSIFICAR", "ambientes": [x for x in p.lados if x]}
              for p in paredes if p.altura_texto is not None]
    return {**info, "paredes": len(paredes), "por_sistema": resumo_paredes(paredes), "paredes_baixas": baixas,
            "aviso": "Pré-classificação automática: material e espessura lidos da arquitetura; chapas, "
                     "perfil e tijolo/bloco inferidos. Confira no CAD antes de gerar a planilha."}
