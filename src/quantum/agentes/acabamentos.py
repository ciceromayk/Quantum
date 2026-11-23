"""Agente de acabamentos: piso, parede e teto por ambiente, lidos da planta de acabamentos.

Fontes, todas do próprio desenho:
- Quadro de acabamentos: textos "ESPECIFICAÇÃO - PISO/PAREDE/TETO/RODAPÉ" com a lista de
  códigos (01, 02...) e descrições ao lado.
- Etiqueta de cada ambiente: bloco com 3 atributos de 2 dígitos. A posição de cada número
  (regras: acabamentos.etiqueta) diz se é piso, parede ou teto.
- Rótulo do ambiente: nome + área declarada ("SUÍTE CASAL 11,05 m2").
- Contorno do ambiente (opcional): polilinha fechada que contém o rótulo e cuja área bate
  com a declarada. Sem contorno, piso e teto usam a área declarada e a parede fica pendente.

Alturas de revestimento de parede NÃO são presumidas. Vêm de parâmetros
`altura_parede_<código>` (metros, ou "teto" para usar o pé-direito) ou, no futuro, dos cortes.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from ..geometria import ponto_no_poligono
from ..ingestao import ler_rotulo
from ..modelos import Desenho, Entidade, ItemQuantitativo, Pendencia, Severidade

DISC = "acabamentos"
TIPOS = ("piso", "parede", "teto", "rodape")
NOME_TIPO = {"piso": "Piso", "parede": "Parede", "teto": "Teto", "rodape": "Rodapé"}
RX_CODIGO = re.compile(r"\d{2}")

AVISO_ALTURAS = (
    "Alturas de revestimento de parede tiradas de cortes valem só para os ambientes que aparecem "
    "cortados e precisam de conferência. Ambientes fora dos cortes ficam como pendência até a "
    "altura ser informada."
)


@dataclass
class Ambiente:
    nome: str
    area_rotulo: float
    ponto: tuple[float, float]
    handle: str
    codigos: dict[str, str] = field(default_factory=dict)  # tipo -> código
    etiqueta_handle: str | None = None
    contorno: list[tuple[float, float]] | None = None
    contorno_handle: str | None = None
    area_contorno_m2: float | None = None
    perimetro_m: float | None = None


def _m2(v: float) -> str:
    return f"{v:.2f}".replace(".", ",") + " m²"


def _perimetro(pts: list[tuple[float, float]]) -> float:
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


class AgenteAcabamentos:
    def __init__(self, config: dict, parametros: dict | None = None):
        self.cfg = config or {}
        self.par = parametros or {}
        self.posicoes: dict[str, str] = self.cfg.get("etiqueta") or {}
        self.dist_max_m = float(self.cfg.get("distancia_max_etiqueta_m", 1.0))
        self.tol_area = float(self.cfg.get("tolerancia_area_contorno", 0.05))
        self.cabecalhos = {k: re.compile(v, re.IGNORECASE) for k, v in (self.cfg.get("cabecalhos") or {}).items()}

    # ------------------------------------------------------------------ leitura
    def ler_quadro(self, d: Desenho, f: float) -> dict[str, dict[str, str]]:
        """Catálogo {tipo: {código: descrição}} lido dos textos do quadro."""
        textos = [e for e in d.entidades if e.tipo in ("TEXT", "MTEXT") and e.texto and e.insercao]
        cab = [(t, e) for e in textos for t, rx in self.cabecalhos.items() if rx.search(e.texto)]
        codigos = [e for e in textos if RX_CODIGO.fullmatch(e.texto.strip())]
        tol_y, max_dx, max_dy = 0.12 / f, 8.0 / f, 8.0 / f
        cat: dict[str, dict[str, str]] = {t: {} for t in TIPOS}
        for c in codigos:
            cx, cy = c.insercao
            cand = [
                (h.insercao[1] - cy, t)
                for t, h in cab
                if 0 < h.insercao[1] - cy <= max_dy and 0 <= h.insercao[0] - cx <= max_dx
            ]
            if not cand:
                continue
            tipo = min(cand)[1]
            desc = [
                e for e in textos
                if e is not c and 0 < e.insercao[0] - cx <= 1.0 / f and abs(e.insercao[1] - cy) <= tol_y
                and not RX_CODIGO.fullmatch(e.texto.strip())
            ]
            if desc:
                cat[tipo].setdefault(c.texto.strip(), min(desc, key=lambda e: e.insercao[0]).texto)
        return {t: v for t, v in cat.items() if v}

    def _etiqueta(self, e: Entidade) -> dict[str, str] | None:
        at = [a for a in e.atributos if RX_CODIGO.fullmatch(a[0])]
        if len(at) != 3 or len(e.atributos) != 3 or not self.posicoes:
            return None
        xs = [a[1] for a in at]
        ys = [a[2] for a in at]
        mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        if max(xs) - min(xs) <= 0 or max(ys) - min(ys) <= 0:
            return None
        out = {}
        for txt, x, y in at:
            pos = ("sup" if y > my else "inf") + ("_esq" if x < mx else "_dir")
            tipo = self.posicoes.get(pos)
            if tipo:
                out[tipo] = txt
        return out or None

    # ------------------------------------------------------------------ execução
    def executar(self, d: Desenho) -> tuple[list[ItemQuantitativo], list[Pendencia], dict]:
        itens: list[ItemQuantitativo] = []
        pend: list[Pendencia] = []
        if not self.posicoes:
            return itens, pend, {}
        f = d.fator_m
        etiquetas = [(e, cod) for e in d.entidades if e.tipo == "INSERT" and (cod := self._etiqueta(e))]
        if not etiquetas:
            return itens, pend, {}  # desenho sem planta de acabamentos: o agente não se aplica
        if not f:
            pend.append(Pendencia(DISC, Severidade.BLOQUEANTE, "Acabamentos não calculados: unidade do desenho desconhecida.",
                                  acao_sugerida="Informe a unidade do desenho."))
            return itens, pend, {}

        catalogo = self.ler_quadro(d, f)
        ambientes: list[Ambiente] = []
        for e in d.entidades:
            if e.area_rotulo is None or not e.ponto_texto:
                continue
            nome = e.texto if e.tipo == "INSERT" else (ler_rotulo([e.texto or ""]) or (e.texto, 0))[0]
            ambientes.append(Ambiente(nome=nome or "?", area_rotulo=e.area_rotulo, ponto=e.ponto_texto, handle=e.handle))

        # Associação etiqueta -> ambiente: pares mais próximos primeiro, cada um usado uma vez.
        pares = sorted(
            (math.dist(a.ponto, (et.atributos[0][1], et.atributos[0][2])) * f, i, j)
            for i, a in enumerate(ambientes) for j, (et, _) in enumerate(etiquetas)
        )
        usados_a, usados_e = set(), set()
        for dist, i, j in pares:
            if dist > self.dist_max_m:
                break
            if i in usados_a or j in usados_e:
                continue
            usados_a.add(i)
            usados_e.add(j)
            ambientes[i].codigos = dict(etiquetas[j][1])
            ambientes[i].etiqueta_handle = etiquetas[j][0].handle

        sem = [a for a in ambientes if not a.codigos]
        if sem:
            pend.append(Pendencia(
                DISC, Severidade.ALERTA,
                f"{len(sem)} ambiente(s) sem etiqueta de acabamento: " + ", ".join(f"{a.nome} ({_m2(a.area_rotulo)})" for a in sem[:10]),
                handles=[a.handle for a in sem],
                acao_sugerida="Coloque a etiqueta no projeto ou confirme que o ambiente não recebe acabamento.",
            ))
        orfas = [etiquetas[j][0] for j in range(len(etiquetas)) if j not in usados_e]
        if orfas:
            pend.append(Pendencia(DISC, Severidade.ALERTA, f"{len(orfas)} etiqueta(s) de acabamento sem rótulo de ambiente próximo.",
                                  handles=[e.handle for e in orfas]))

        self._contornos(d, ambientes, f)

        fora = sorted({(t, c) for a in ambientes for t, c in a.codigos.items() if c not in catalogo.get(t, {})})
        if fora:
            pend.append(Pendencia(DISC, Severidade.ALERTA,
                                  "Código(s) nas etiquetas que não estão no quadro de acabamentos: " + ", ".join(f"{NOME_TIPO[t]} {c}" for t, c in fora),
                                  acao_sugerida="Confira o quadro de acabamentos do projeto."))

        dif = [a for a in ambientes if a.area_contorno_m2 is not None and abs(a.area_contorno_m2 - a.area_rotulo) > 0.01 * a.area_rotulo]
        if dif:
            pend.append(Pendencia(
                DISC, Severidade.ALERTA,
                "Contorno com área diferente do rótulo (mais de 1%): "
                + ", ".join(f"{a.nome} ({_m2(a.area_contorno_m2)} × {_m2(a.area_rotulo)})" for a in dif[:10]),
                handles=[a.contorno_handle for a in dif if a.contorno_handle],
                acao_sugerida="Confira se a polilinha é mesmo o contorno do ambiente.",
            ))
        com_contorno = sum(a.contorno is not None for a in ambientes if a.codigos)
        for tipo in ("piso", "teto"):
            itens += self._areas(tipo, ambientes, catalogo)
        itens += self._paredes(ambientes, catalogo, pend)

        if com_contorno == 0:
            pend.append(Pendencia(
                DISC, Severidade.ALERTA,
                "Ambientes sem contorno: piso e teto usam a área declarada nos rótulos e a parede não pode ser medida.",
                acao_sugerida="Exporte o DXF com o contorno (polígono) das zonas de ambiente.",
            ))
        pend.append(Pendencia(DISC, Severidade.INFO, AVISO_ALTURAS))
        if "rodape" not in self.posicoes.values():
            pend.append(Pendencia(DISC, Severidade.INFO, "Rodapé não consta na etiqueta dos ambientes e não foi quantificado."))

        resumo = {
            "catalogo": catalogo,
            "codigos_parede": sorted({a.codigos["parede"] for a in ambientes if "parede" in a.codigos}),
            "aviso_alturas": AVISO_ALTURAS,
            "ambientes": [
                {
                    "nome": a.nome, "area_rotulo": a.area_rotulo, "codigos": a.codigos,
                    "area_contorno_m2": a.area_contorno_m2, "perimetro_m": a.perimetro_m,
                    "contorno": a.contorno, "handle": a.handle, "contorno_handle": a.contorno_handle,
                }
                for a in ambientes
            ],
        }
        return itens, pend, resumo

    def _contornos(self, d: Desenho, ambientes: list[Ambiente], f: float) -> None:
        fechadas = [e for e in d.entidades if e.fechada and e.area > 0 and len(e.pontos) >= 4]
        for a in ambientes:
            cand = [e for e in fechadas if ponto_no_poligono(a.ponto, e.pontos)]
            ok = [e for e in cand if abs(e.area * f * f - a.area_rotulo) <= self.tol_area * a.area_rotulo]
            if ok:
                e = min(ok, key=lambda x: abs(x.area * f * f - a.area_rotulo))
                a.contorno, a.contorno_handle = e.pontos, e.handle
                a.area_contorno_m2 = e.area * f * f
                a.perimetro_m = _perimetro(e.pontos) * f

    def _areas(self, tipo: str, ambientes: list[Ambiente], catalogo: dict) -> list[ItemQuantitativo]:
        grupos: dict[str, list[Ambiente]] = {}
        for a in ambientes:
            if tipo in a.codigos:
                grupos.setdefault(a.codigos[tipo], []).append(a)
        out = []
        for cod in sorted(grupos):
            amb = grupos[cod]
            medidos = [a for a in amb if a.area_contorno_m2 is not None]
            q = sum(a.area_contorno_m2 if a.area_contorno_m2 is not None else a.area_rotulo for a in amb)
            obs = f"{len(amb)} ambiente(s). "
            obs += "Área medida no contorno." if len(medidos) == len(amb) else (
                f"Área declarada nos rótulos em {len(amb) - len(medidos)} ambiente(s), não medida.")
            out.append(ItemQuantitativo(
                disciplina=DISC, codigo=f"ACB-{tipo.upper()}-{cod}",
                descricao=f"{NOME_TIPO[tipo]} {cod}: {catalogo.get(tipo, {}).get(cod, 'código fora do quadro')}",
                unidade="m²", quantidade=round(q, 4), detalhe=", ".join(sorted({a.nome for a in amb}))[:200],
                handles=[a.handle for a in amb], observacao=obs,
            ))
        return out

    def _altura(self, cod: str) -> float | None:
        v = self.par.get(f"altura_parede_{cod}")
        if v is None or v == "":
            return None
        if isinstance(v, str) and v.strip().lower() == "teto":
            pd = self.par.get("pe_direito")
            return float(pd) if isinstance(pd, (int, float)) else None
        return float(v)

    def _paredes(self, ambientes: list[Ambiente], catalogo: dict, pend: list[Pendencia]) -> list[ItemQuantitativo]:
        grupos: dict[str, list[Ambiente]] = {}
        for a in ambientes:
            if "parede" in a.codigos:
                grupos.setdefault(a.codigos["parede"], []).append(a)
        out = []
        for cod in sorted(grupos):
            amb = grupos[cod]
            h = self._altura(cod)
            medidos = [a for a in amb if a.perimetro_m is not None]
            q = None
            if h is not None and medidos and len(medidos) == len(amb):
                q = round(sum(a.perimetro_m for a in amb) * h, 4)
            if h is None:
                pend.append(Pendencia(
                    DISC, Severidade.BLOQUEANTE,
                    f"Parede {cod}: altura do revestimento não informada.",
                    acao_sugerida=f"Envie os cortes ou informe altura_parede_{cod} (m, ou 'teto' com o pé-direito).",
                ))
            obs = f"{len(amb)} ambiente(s). Perímetro do contorno × altura, sem descontar vãos de portas e janelas."
            if len(medidos) < len(amb):
                obs = f"{len(amb) - len(medidos)} de {len(amb)} ambiente(s) sem contorno: área não medida."
            out.append(ItemQuantitativo(
                disciplina=DISC, codigo=f"ACB-PAREDE-{cod}",
                descricao=f"Parede {cod}: {catalogo.get('parede', {}).get(cod, 'código fora do quadro')}",
                unidade="m²", quantidade=q, detalhe=", ".join(sorted({a.nome for a in amb}))[:200],
                handles=[a.handle for a in amb], observacao=obs,
            ))
        return out
