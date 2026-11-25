"""Agente de paredes e painéis: lê a PLANTA FALADA e monta a planilha padrão de quantitativo.

Planta falada = a planta de arquitetura com uma polilinha no eixo de cada parede, numa camada
por sistema (ex.: `0_DRY_WALL_70mm_+ST+ST`, `0_TIJOLO CERAMICO_14CM`). O comprimento das
polilinhas de cada camada é o perímetro da parede daquele sistema.

Cada linha da planilha é um sistema de parede num ambiente de uma coluna (tipo de unidade):
perímetro × altura − vãos, e daí os insumos (chapas por face, perfis, marcação, alvenaria).

- Altura = pé-esquerdo (piso a piso) − contrapiso − elemento estrutural (laje, ou viga onde a
  planta anota "H=2,28M", que é a altura livre sob a viga).
- Vãos: o ID escrito na planta (P01, J14, V05…) junto da parede, com largura e altura do quadro
  de esquadrias. Só vão com área acima de 2 m² entra no desconto.
- Coluna e ambiente vêm dos textos da planta (COLUNA 0x, nome dos ambientes). A atribuição é
  automática e precisa de conferência.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

from ..modelos import Desenho, ItemQuantitativo, Pendencia, Severidade

DISC = "paredes"
LIMITE_VAO_M2 = 2.0

# camada da planta falada -> especificação (nome da planilha padrão)
CAMADAS_PADRAO: list[tuple[str, str]] = [
    (r"DRY[\s_-]*WALL[\s_-]*48\s*MM.*\+\s*RU", "PERFIL 48MM + RU"),
    (r"DRY[\s_-]*WALL[\s_-]*70\s*MM.*\+\s*RU\s*\+\s*RU", "PERFIL 70MM + RU + RU"),
    (r"DRY[\s_-]*WALL[\s_-]*70\s*MM.*\+\s*ST\s*\+\s*RU", "PERFIL 70MM + ST + RU"),
    (r"DRY[\s_-]*WALL[\s_-]*70\s*MM.*\+\s*ST\s*\+\s*ST", "PERFIL 70MM + ST + ST"),
    (r"STEEL[\s_-]*FRAME[\s_-]*90\s*MM.*GR\s*\+\s*GR", "PERFIL STEEL FRAME 90MM + GR + GR"),
    (r"STEEL[\s_-]*FRAME[\s_-]*90\s*MM.*GR\s*\+\s*RU", "PERFIL STEEL FRAME 90MM + GR + RU"),
    (r"STEEL[\s_-]*FRAME[\s_-]*90\s*MM.*GR\s*\+\s*ST", "PERFIL STEEL FRAME 90MM + GR + ST"),
    (r"STEEL[\s_-]*FRAME[\s_-]*90\s*MM.*ST\s*\+\s*RU", "PERFIL STEEL FRAME 90MM + ST + RU"),
    (r"STEEL[\s_-]*FRAME[\s_-]*90\s*MM.*ST\s*\+\s*ST", "PERFIL STEEL FRAME 90MM + ST + ST"),
    (r"TIJOLO[\s_-]*CERAMICO[\s_-]*9\s*CM", "ALVENARIA TIJOLO DE 9CM"),
    (r"TIJOLO[\s_-]*CERAMICO[\s_-]*14\s*CM", "ALVENARIA TIJOLO DE 14CM"),
    (r"TIJOLO[\s_-]*CERAMICO[\s_-]*19\s*CM", "ALVENARIA TIJOLO DE 19CM"),
    (r"BLOCO[\s_-]*DE[\s_-]*CONCRETO[\s_-]*14\s*CM", "BLOCO DE CONCRETO DE 14CM"),
]

# ambiente da linha pelo sistema, dentro das unidades (convenção da planilha padrão do escritório)
AMBIENTE_POR_ESPEC = {
    "PERFIL 70MM + ST + ST": "SUÍTES",
    "PERFIL 70MM + ST + RU": "WC/A.SERV.",
    "PERFIL 70MM + RU + RU": "WC",
    "PERFIL 48MM + RU": "SHAFT",
    "PERFIL STEEL FRAME 90MM + GR + ST": "VARANDA",
}

# ambientes de uso comum: a linha sai da coluna e vai para o grupo do ambiente
COMUNS = {
    "ESCADA": "CX DE ESCADA", "ANTE": "CX DE ESCADA", "CAMARA": "CX DE ESCADA", "ANTECAMARA": "CX DE ESCADA",
    "ELEVADOR": "CIRCULAÇÃO", "HALL": "CIRCULAÇÃO", "LIXO": "CIRCULAÇÃO", "LAJE TECNICA": "LAJE TÉCNICA",
}
AREA_CIRCULACAO_COMUM_M2 = 20.0  # circulação maior que isso é a do andar, não a da unidade

ESPECIFICACOES = [e for _, e in CAMADAS_PADRAO]

RX_ID_VAO = re.compile(r"^(P|J|V|PE|PJ|PV|JA|BS)\d{0,3}$")
RX_H = re.compile(r"^H\s*=\s*(\d+[.,]\d+)\s*M?$", re.IGNORECASE)
# parede baixa com a altura escrita no desenho: "MURETA h=0,20m (ACABADO)", "PEITORIL h=1,20m"
RX_PAREDE_BAIXA = re.compile(r"\b(MURETA|PEITORIL|GUARDA\s*-?\s*CORPO)\b.*?\bH\s*=\s*(\d+(?:[.,]\d+)?)\s*M?\b", re.IGNORECASE)
DIST_TEXTO_ALTURA_M = 1.0
RX_AREA = re.compile(r"^\d+[.,]\d+$")
NAO_NOME = re.compile(r"^(\d|D$|M$|M2$|M²$|B$|A$|PCF$|UND|COLUNA|PROJE|A=|ST-|GR-|RU-|LEGENDA|DESCRI|LAYERS)")


def _chave(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.replace(".", " ")).strip().upper()


def especificacao_da_camada(camada: str, mapa: list[tuple[str, str]] | None = None) -> str | None:
    k = _chave(camada)
    for rx, esp in mapa or CAMADAS_PADRAO:
        if re.search(rx, k, re.IGNORECASE):
            return esp
    return None


def faces(esp: str) -> dict[str, int]:
    """Chapas por face: "PERFIL 70MM + ST + RU" -> {"ST": 1, "RU": 1}."""
    out: dict[str, int] = {}
    if esp.startswith("PERFIL"):
        for c in re.findall(r"\+\s*(ST|RU|GR)\b", esp):
            out[c] = out.get(c, 0) + 1
    return out


def perfil(esp: str) -> str | None:
    if esp.startswith("PERFIL 48MM"):
        return "48"
    if esp.startswith("PERFIL 70MM"):
        return "70"
    if esp.startswith("PERFIL STEEL FRAME 90MM"):
        return "90"
    return None


@dataclass
class Trecho:
    esp: str
    camada: str
    handle: str
    pontos: list[tuple[float, float]]
    comprimento_m: float
    coluna: str = ""
    ambiente: str = ""
    classificacao: str = "GERAL"
    altura_livre: float | None = None  # "H=2,28M" anotado junto da parede
    altura_texto: float | None = None  # parede baixa: altura escrita no desenho (MURETA h=0,20m)
    texto_altura: str = ""
    vaos: list[str] = field(default_factory=list)


def alturas_de_texto(textos) -> tuple[list[tuple[float, str, float, float]], list[str]]:
    """Textos de parede baixa com altura: (altura m, texto, x, y). Também devolve os textos
    ambíguos (guarda-corpo + mureta com uma altura só: a altura é do guarda-corpo)."""
    ok, ambiguos = [], []
    for t, x, y, *_ in textos:
        m = RX_PAREDE_BAIXA.search(t)
        if not m:
            continue
        k = _chave(t)
        if re.search(r"GUARDA\s*-?\s*CORPO", k) and "MURETA" in k and len(re.findall(r"\bH\s*=", k)) == 1:
            ambiguos.append(t)
            continue
        ok.append((_num(m.group(2)), t, x, y))
    return ok, ambiguos


def _dist_ponto_polilinha(p, pts) -> float:
    best = math.inf
    for a, b in zip(pts, pts[1:]):
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
        best = min(best, math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy))
    return best


def _meio(pts):
    tot = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        if acc + d >= tot / 2 and d > 0:
            t = (tot / 2 - acc) / d
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        acc += d
    return pts[0]


def _num(t: str) -> float:
    return float(t.replace(",", "."))


class AgentePaineis:
    def __init__(self, config: dict | None = None, parametros: dict | None = None, pavimento: str = "PAVIMENTO TIPO",
                 repeticoes: int = 1):
        cfg = config or {}
        self.mapa = [(c["padrao"], c["especificacao"]) for c in cfg.get("camadas", [])] or CAMADAS_PADRAO
        self.amb_por_esp = {**AMBIENTE_POR_ESPEC, **(cfg.get("ambiente_por_especificacao") or {})}
        self.par = parametros or {}
        self.pavimento = pavimento
        self.rep = max(1, int(repeticoes or 1))

    # ------------------------------------------------------------------ parâmetros
    def _p(self, k: str) -> float | None:
        v = self.par.get(k)
        return float(v) if isinstance(v, (int, float)) else None

    def quadro(self) -> dict[str, dict]:
        """Quadro de esquadrias informado: vao_<ID>_largura, vao_<ID>_altura (m)."""
        out: dict[str, dict] = {}
        for k, v in self.par.items():
            m = re.fullmatch(r"vao_(.+)_(largura|altura|peitoril)", k)
            if m and isinstance(v, (int, float)):
                out.setdefault(m.group(1).upper(), {})[m.group(2)] = float(v)
        return out

    # ------------------------------------------------------------------ leitura
    def _textos(self, msp) -> list[tuple[str, float, float, float]]:
        out = []

        def add(e):
            t = e.dxftype()
            if t not in ("TEXT", "MTEXT"):
                return
            s = e.plain_text() if t == "MTEXT" else e.dxf.text
            s = re.sub(r"\s+", " ", (s or "")).strip()
            if s:
                out.append((s, e.dxf.insert.x, e.dxf.insert.y, float(e.dxf.get("rotation", 0) or 0)))

        for e in msp:
            if e.dxftype() == "INSERT":
                for a in getattr(e, "attribs", []):  # atributos (ATTRIB) presos ao bloco: virtual_entities não os traz
                    s = re.sub(r"\s+", " ", (a.dxf.text or "")).strip()
                    if s:
                        out.append((s, a.dxf.insert.x, a.dxf.insert.y, float(a.dxf.get("rotation", 0) or 0)))
                try:
                    for v in e.virtual_entities():
                        add(v)
                except Exception:
                    continue
            else:
                add(e)
        return out

    def executar(self, d: Desenho) -> tuple[list[ItemQuantitativo], list[Pendencia], dict]:
        msp = getattr(d, "modelspace", None)
        if msp is None:
            return [], [], {}
        brutos = []
        for e in msp.query("LWPOLYLINE LINE POLYLINE"):
            esp = especificacao_da_camada(e.dxf.layer, self.mapa)
            if not esp:
                continue
            if e.dxftype() == "LINE":
                pts = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
            elif e.dxftype() == "LWPOLYLINE":
                pts = [(x, y) for x, y in e.get_points("xy")]
                if e.closed:
                    pts.append(pts[0])
            else:
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            if len(pts) >= 2:
                brutos.append((esp, e.dxf.layer, e.dxf.handle, pts))
        if not brutos:
            return [], [], {}  # não é planta falada
        pend: list[Pendencia] = []
        # amostras da legenda (quadro de alvenarias) estão nas mesmas camadas: ficam de fora
        legenda = self._caixa_legenda(msp)
        if legenda:
            lx0, ly0, lx1, ly1 = legenda
            fora = [b for b in brutos if not all(lx0 <= x <= lx1 and ly0 <= y <= ly1 for x, y in b[3])]
            if len(fora) < len(brutos):
                pend.append(Pendencia(DISC, Severidade.INFO,
                                      f"{len(brutos) - len(fora)} polilinha(s) da legenda de alvenarias não entraram na medição."))
            brutos = fora

        # unidade: o cabeçalho às vezes diz mm com o desenho em metros (export do ArchiCAD/GstarCAD)
        f = d.fator_m or 1.0
        xs = [p[0] for *_, pts in brutos for p in pts]
        ys = [p[1] for *_, pts in brutos for p in pts]
        extensao = max(max(xs) - min(xs), max(ys) - min(ys))
        if extensao * f < 3.0 and extensao > 3.0:
            pend.append(Pendencia(DISC, Severidade.ALERTA,
                                  f"O cabeçalho diz {d.unidade or '?'}, mas as paredes medem {extensao:.0f} unidades de ponta a ponta: "
                                  "li o desenho em METROS.", acao_sugerida="Confira a unidade do desenho em Parâmetros."))
            f = 1.0
        trechos = [Trecho(esp, cam, h, pts, sum(math.dist(a, b) for a, b in zip(pts, pts[1:])) * f)
                   for esp, cam, h, pts in brutos]
        caixa = (min(xs), min(ys), max(xs), max(ys))
        textos = self._textos(msp)
        self._atribuir(trechos, textos, caixa, f, pend, self._chamadas(msp, f))
        linhas, esquadrias = self._linhas(trechos, pend)
        itens = self._itens(linhas)
        resumo = {
            "pavimento": self.pavimento,
            "linhas": linhas,
            "esquadrias": esquadrias,
            "parametros_altura": {k: self.par.get(k) for k in ("pe_esquerdo", "contrapiso", "espessura_laje")},
            "aviso": "Coluna e ambiente de cada parede foram atribuídos automaticamente pelos textos da planta; confira.",
        }
        return itens, pend, resumo

    @staticmethod
    def _caixa_legenda(msp):
        from ezdxf import bbox

        ents = [e for e in msp if re.search(r"QUADRO|LEGENDA", e.dxf.get("layer", ""), re.IGNORECASE)]
        if not ents:
            return None
        b = bbox.extents(ents)
        return (b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y) if b.has_data else None

    @staticmethod
    def _chamadas(msp, f: float = 1.0) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """Linhas de chamada das notas: (ponta com o círculo, ponta na parede). f = metros por unidade."""
        circulos = [(e.dxf.center.x, e.dxf.center.y) for e in msp.query("CIRCLE") if e.dxf.radius * f < 0.3]
        out = []
        for e in msp.query("LINE LWPOLYLINE"):
            if e.dxftype() == "LINE":
                a, b = (e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)
            elif not e.closed:
                pts = [(x, y) for x, y in e.get_points("xy")]
                if len(pts) < 2:
                    continue
                a, b = pts[0], pts[-1]
            else:
                continue
            for c in circulos:
                if math.dist(c, a) * f < 0.05:
                    out.append((a, b))
                elif math.dist(c, b) * f < 0.05:
                    out.append((b, a))
        return out

    # ------------------------------------------------------------------ atribuição
    def _atribuir(self, trechos: list[Trecho], textos, caixa, f: float, pend: list[Pendencia], chamadas=()) -> None:
        x0, y0, x1, y1 = caixa
        # rótulos de coluna fora do desenho das paredes: abaixo (texto deitado) ou ao lado (em pé)
        colunas = [(t, x, y, r) for t, x, y, r in textos if t.upper().startswith("COLUNA")
                   and not (x0 <= x <= x1 and y0 <= y <= y1)]
        deitados = [(t, x, y) for t, x, y, r in colunas if abs(r % 180) < 45]
        em_pe = [(t, x, y) for t, x, y, r in colunas if abs(r % 180) >= 45]
        # ambientes: nome + área logo abaixo
        areas = [(x, y, _num(t)) for t, x, y, _ in textos if RX_AREA.match(t)]
        nomes = []
        for t, x, y, _ in textos:
            if (mb := RX_PAREDE_BAIXA.search(t)):
                t = t[:mb.start()]  # texto misto (ESCADA + MURETA h=…): fica só o nome do ambiente
            k = _chave(t)
            if len(k) < 2 or NAO_NOME.match(k) or RX_ID_VAO.match(k) or RX_H.match(t) or len(k) > 30:
                continue
            perto = [(math.hypot(ax - x, ay - y), a) for ax, ay, a in areas if 0 < y - ay < 1.0 / f and abs(ax - x) < 1.5 / f]
            area = min(perto)[1] if perto else None
            nomes.append((k, x, y, area))
        ids = [(_chave(t).replace(" ", ""), x, y) for t, x, y, _ in textos if RX_ID_VAO.match(_chave(t).replace(" ", ""))]
        alturas = [(_num(m.group(1)), x, y) for t, x, y, _ in textos if (m := RX_H.match(t))]

        for tr in trechos:
            m = _meio(tr.pontos)
            # ambiente mais próximo da parede (pelo rótulo)
            amb = min(nomes, key=lambda n: _dist_ponto_polilinha((n[1], n[2]), tr.pontos)) if nomes else None
            nome_amb, area_amb = (amb[0], amb[3]) if amb else ("", None)
            comum = next((g for k, g in COMUNS.items() if nome_amb.startswith(k)), None)
            if nome_amb.startswith("CIRCULACAO") and (area_amb or 0) > AREA_CIRCULACAO_COMUM_M2:
                comum = "CIRCULAÇÃO"
            if tr.esp.startswith(("ALVENARIA", "BLOCO")):
                tr.coluna = tr.ambiente = "CX DE ESCADA" if comum == "CX DE ESCADA" else "GERAL"
                tr.classificacao = "CX DE ESCADA" if comum == "CX DE ESCADA" and tr.esp.startswith("BLOCO") else "GERAL"
            elif comum:
                tr.coluna = comum
                tr.ambiente = self.amb_por_esp.get(tr.esp, comum) if tr.esp == "PERFIL 48MM + RU" else comum
                tr.classificacao = "HALL" if comum == "CIRCULAÇÃO" and tr.esp == "PERFIL 48MM + RU" else "GERAL"
            else:
                tr.coluna = self._coluna(m, deitados, em_pe, caixa)
                tr.ambiente = self.amb_por_esp.get(tr.esp) or re.sub(r"\s*\d+$", "", nome_amb) or "?"

        # altura livre anotada (H=2,28M): a nota aponta a parede pela linha de chamada (círculo
        # junto da nota, a outra ponta na parede); sem chamada, só a parede a até 0,5 m da nota
        sem_alvo = []
        for h, x, y in alturas:
            alvo = None
            ch = [(math.dist(c, (x, y)), p) for c, p in chamadas]
            ch = [c for c in ch if c[0] * f <= 1.5]
            ponto = min(ch)[1] if ch else (x, y)
            lim = 0.6 if ch else 0.5
            cand = [(_dist_ponto_polilinha(ponto, tr.pontos) * f, i) for i, tr in enumerate(trechos)]
            dmin, i = min(cand)
            if dmin <= lim:
                alvo = trechos[i]
                alvo.altura_livre = h
            else:
                sem_alvo.append(f"H={h:.2f}".replace(".", ","))
        if sem_alvo:
            pend.append(Pendencia(DISC, Severidade.ALERTA,
                                  f"Nota(s) de altura sem parede identificada: {', '.join(sem_alvo)}. Não foram usadas.",
                                  acao_sugerida="Ligue a nota à parede com uma linha de chamada."))
        # cada ID de vão vai para a parede mais próxima (até 1 m)
        for vid, x, y in ids:
            cand = [(_dist_ponto_polilinha((x, y), tr.pontos) * f, i) for i, tr in enumerate(trechos)]
            dmin, i = min(cand)
            if dmin <= 1.0:
                trechos[i].vaos.append(vid)
        # parede baixa: texto MURETA/PEITORIL/GUARDA-CORPO com h= a até 1 m da parede
        baixas, ambiguos = alturas_de_texto(textos)
        for h, t, x, y in baixas:
            cand = [(_dist_ponto_polilinha((x, y), tr.pontos) * f, i) for i, tr in enumerate(trechos)]
            if not cand:
                break
            dmin, i = min(cand)
            if dmin <= DIST_TEXTO_ALTURA_M:
                trechos[i].altura_texto, trechos[i].texto_altura = h, re.sub(r"\s+", " ", t).strip()
        usados = [tr for tr in trechos if tr.altura_texto is not None]
        if usados:
            lista = "; ".join(sorted({f"{tr.ambiente or '?'}: {tr.texto_altura}" for tr in usados}))
            pend.append(Pendencia(DISC, Severidade.ALERTA,
                                  f"{len(usados)} parede(s) baixa(s) com altura lida do TEXTO DO DESENHO (não do pé-esquerdo): {lista}.",
                                  acao_sugerida="Confira se o texto se refere a essa parede e se a altura é a do trecho de parede."))
        if ambiguos:
            pend.append(Pendencia(DISC, Severidade.ALERTA,
                                  "Texto com guarda-corpo e mureta e uma altura só (a altura é do guarda-corpo): " + "; ".join(sorted(set(ambiguos)))
                                  + ". A altura não foi usada na mureta.",
                                  acao_sugerida="Escreva a altura da mureta no desenho (MURETA h=…) ou ajuste a altura na planilha."))
        if any(t.altura_livre for t in trechos):
            pend.append(Pendencia(DISC, Severidade.ALERTA,
                                  f"{sum(1 for t in trechos if t.altura_livre)} parede(s) com altura anotada na planta (H=…): "
                                  "usei como altura livre sob viga, menos o contrapiso. Confira a qual parede cada nota se refere."))

    @staticmethod
    def _coluna(m, deitados, em_pe, caixa) -> str:
        x0, y0, x1, y1 = caixa
        cand = []
        if deitados:
            yr = sum(y for _, _, y in deitados) / len(deitados)
            t, x, _ = min(deitados, key=lambda c: abs(c[1] - m[0]))
            cand.append((abs(m[1] - yr), t))
        if em_pe:
            xr = sum(x for _, x, _ in em_pe) / len(em_pe)
            t, _, y = min(em_pe, key=lambda c: abs(c[2] - m[1]))
            cand.append((abs(m[0] - xr), t))
        return min(cand)[1].upper() if cand else "?"

    # ------------------------------------------------------------------ linhas da planilha
    def _altura(self, tr: Trecho) -> tuple[float | None, str, float | None]:
        """(altura, elemento estrutural, altura do elemento)."""
        if tr.altura_texto is not None:  # parede baixa: a altura vem do texto do desenho
            return tr.altura_texto, f"{tr.texto_altura} (TEXTO DO DESENHO)", 0.0
        pe, cp, laje = self._p("pe_esquerdo"), self._p("contrapiso"), self._p("espessura_laje")
        if pe is None or cp is None:
            return None, "", None
        if tr.altura_livre is not None:
            return round(tr.altura_livre - cp, 4), "VIGA", round(pe - tr.altura_livre, 4)
        if laje is None:
            return None, "LAJE", None
        return round(pe - cp - laje, 4), "LAJE", laje

    def _linhas(self, trechos: list[Trecho], pend: list[Pendencia]) -> tuple[list[dict], list[dict]]:
        quadro = self.quadro()
        # agrupa por coluna/ambiente/classificação/sistema/altura
        grupos: dict[tuple, dict] = {}
        for tr in trechos:
            h, elem, h_elem = self._altura(tr)
            k = (tr.coluna, tr.ambiente, tr.classificacao, tr.esp, elem, h_elem)
            g = grupos.setdefault(k, {"perimetro": 0.0, "vaos": [], "handles": [], "altura": h})
            g["perimetro"] += tr.comprimento_m
            g["vaos"] += tr.vaos
            g["handles"].append(tr.handle)
        # colunas iguais (mesmo sistema, ambiente, perímetro e vãos) viram uma linha com QTDE
        juntas: dict[tuple, dict] = {}
        for (col, amb, cla, esp, elem, h_elem), g in grupos.items():
            chave = (amb, cla, esp, elem, h_elem, round(g["perimetro"], 2), tuple(sorted(g["vaos"])),
                     col if not col.startswith("COLUNA") else "COLUNA")
            j = juntas.setdefault(chave, {"colunas": [], **g, "elemento": elem, "altura_elemento": h_elem,
                                          "ambiente": amb, "classificacao": cla, "especificacao": esp})
            j["colunas"].append(col)
            if j is not g and j["colunas"] != [col]:
                j["handles"] = j["handles"] + g["handles"]
        sem_quadro: set[str] = set()
        linhas = []
        for j in juntas.values():
            cols = sorted(j["colunas"])
            nome_col = cols[0] if len(cols) == 1 or not cols[0].startswith("COLUNA") else \
                "COLUNA " + "/".join(c.split()[-1] for c in cols)
            area_vaos, descontados = 0.0, []
            for v in j["vaos"]:
                q = quadro.get(v)
                if not q or "largura" not in q or "altura" not in q:
                    sem_quadro.add(v)
                    continue
                a = q["largura"] * q["altura"]
                if a > LIMITE_VAO_M2:  # critério da planilha padrão: desconta a área total do vão
                    area_vaos += a
                    descontados.append(v)
            h = j["altura"]
            area = None if h is None else j["perimetro"] * h
            linhas.append({
                "coluna": nome_col, "pavimento": self.pavimento, "ambiente": j["ambiente"],
                "classificacao": j["classificacao"], "especificacao": j["especificacao"],
                "rep": self.rep, "qtde": len(cols), "perimetro_m": round(j["perimetro"], 4),
                # parede baixa: na planilha, P = L − M − O dá a altura do texto (L = h, M = O = 0)
                **({"pe_esquerdo": h, "contrapiso": 0.0} if j["elemento"].endswith("(TEXTO DO DESENHO)") else
                   {"pe_esquerdo": self._p("pe_esquerdo"), "contrapiso": self._p("contrapiso")}),
                "elemento": j["elemento"], "altura_elemento": j["altura_elemento"], "altura_m": h,
                "origem_altura": "texto do desenho" if j["elemento"].endswith("(TEXTO DO DESENHO)") else
                "nota H= (viga)" if j["elemento"] == "VIGA" else "pé-esquerdo − contrapiso − laje",
                "area_parede_m2": None if area is None else round(area, 4),
                "esquadrias": "/".join(descontados), "area_esquadrias_m2": round(area_vaos, 4),
                "area_total_m2": None if area is None else round(self.rep * len(cols) * (area - area_vaos), 4),
                "vaos_lidos": sorted(j["vaos"]), "handles": j["handles"],
            })
        linhas.sort(key=lambda l: (ESPECIFICACOES.index(l["especificacao"]), not l["coluna"].startswith("COLUNA"), l["coluna"]))
        if sem_quadro:
            pend.append(Pendencia(DISC, Severidade.BLOQUEANTE,
                                  "Esquadrias da planta sem largura e altura no quadro: " + ", ".join(sorted(sem_quadro)) + ".",
                                  acao_sugerida="Preencha o quadro de esquadrias em Parâmetros (largura e altura de cada ID)."))
        if any(l["altura_m"] is None for l in linhas):
            pend.append(Pendencia(DISC, Severidade.BLOQUEANTE,
                                  "Altura das paredes não calculada: informe pé-esquerdo (piso a piso), contrapiso e espessura da laje.",
                                  acao_sugerida="Parâmetros: pe_esquerdo, contrapiso, espessura_laje (m)."))
        todos = sorted({v for l in linhas for v in l["vaos_lidos"]})
        esquadrias = [{"id": v, **quadro.get(v, {}),
                       "area_m2": round(quadro[v]["largura"] * quadro[v]["altura"], 4) if v in quadro and {"largura", "altura"} <= quadro[v].keys() else None}
                      for v in todos]
        return linhas, esquadrias

    # ------------------------------------------------------------------ insumos
    @staticmethod
    def insumos(l: dict) -> dict[str, float]:
        """Mesmas regras das fórmulas da planilha padrão."""
        esp, at = l["especificacao"], l["area_total_m2"]
        out: dict[str, float] = {}
        if at is None:
            return out
        p = perfil(esp)
        if p:
            out[{"48": "ESTRUTURA METÁLICA DRYWALL DE 48MM (M2)", "70": "ESTRUTURA METÁLICA DRYWALL DE 70MM (M2)",
                 "90": "ESTRUTURA METÁLICA STEEL FRAME 90MM (M2)"}[p]] = at
            out["MARCAÇÃO DRYWALL (M2)"] = at
            for c, n in faces(esp).items():
                out[f"CHAPA {c} (M2)"] = out.get(f"CHAPA {c} (M2)", 0) + at * n
        elif esp.startswith("ALVENARIA"):
            out["MARCAÇÃO DE TIJOLO CERÂMICO (M)"] = l["rep"] * l["qtde"] * l["perimetro_m"]
            cm = re.search(r"(\d+)CM", esp).group(1)
            out[f"TIJOLO CERÂMICO {cm}CM (M2)"] = at
        elif esp.startswith("BLOCO"):
            out["MARCAÇÃO DE BLOCO DE CONCRETO (M)"] = l["rep"] * l["qtde"] * l["perimetro_m"]
            out["BLOCO DE CONCRETO DE 14CM (M2)"] = at
        return out

    def _itens(self, linhas: list[dict]) -> list[ItemQuantitativo]:
        tot: dict[str, float | None] = {}
        for l in linhas:
            if l["area_total_m2"] is None:
                for k in ("parede:" + l["especificacao"],):
                    tot[k] = None
                continue
            k = "parede:" + l["especificacao"]
            if tot.get(k, 0) is not None:
                tot[k] = tot.get(k, 0) + l["area_total_m2"]
            for nome, v in self.insumos(l).items():
                tot["insumo:" + nome] = (tot.get("insumo:" + nome) or 0) + v
        itens = []
        for k, v in tot.items():
            tipo, nome = k.split(":", 1)
            un = "m" if "(M)" in nome else "m²"
            itens.append(ItemQuantitativo(
                disciplina=DISC, codigo=("PAR-" if tipo == "parede" else "INS-") + _chave(nome).replace(" ", "-")[:40],
                descricao=nome if tipo == "insumo" else f"Parede {nome}", unidade=un,
                quantidade=None if v is None else round(v, 4),
                observacao="Perímetro da planta falada × (pé-esquerdo − contrapiso − laje/viga), menos vãos acima de 2 m². Sem perdas."
                if tipo == "parede" else "Derivado da área líquida, pelas regras da planilha padrão. Sem perdas.",
            ))
        return itens
