"""Agente auditor: aponta inconsistências e dados faltantes ANTES do orçamento.

Regra de ouro do Quantum: não adivinhar dado técnico. Tudo que o desenho não
permite afirmar com segurança vira uma `Pendencia`, com a ação sugerida.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from ..geometria import assinatura, ponto_no_poligono
from ..ingestao import TIPOS_LINEARES, TIPOS_TEXTO
from ..modelos import Desenho, Entidade, Pendencia, Severidade
from ..regras import Regras

DISCIPLINA = "Auditoria"

# "12,50 m²", "A=12.5m2", "ÁREA: 12,50 M2"
RX_AREA_TEXTO = re.compile(r"(\d+(?:[.,]\d+)?)\s*m(?:²|2)\b", re.IGNORECASE)
TOLERANCIA_AREA = 0.02  # 2 %


def _virgula(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def texto_e_area(texto: str) -> bool:
    return bool(RX_AREA_TEXTO.search(texto))


class AgenteAuditor:
    def __init__(self, regras: Regras):
        self.regras = regras

    def auditar(
        self,
        desenho: Desenho,
        camadas_usadas: set[str],
        medidas_por_item: dict[str, list[Entidade]],
        itens_area_rotulada: set[str],
    ) -> tuple[list[Pendencia], dict[str, int]]:
        p: list[Pendencia] = []
        p += self._unidade(desenho)
        p += self._vazio(desenho)
        nao_classificadas = self._nao_classificadas(desenho, camadas_usadas)
        if nao_classificadas:
            lista = ", ".join(f"{c} ({n})" for c, n in sorted(nao_classificadas.items()))
            p.append(
                Pendencia(
                    disciplina=DISCIPLINA,
                    severidade=Severidade.ALERTA,
                    mensagem=f"{len(nao_classificadas)} camada(s) com geometria não classificadas em disciplina: {lista}",
                    acao_sugerida="Adicione essas camadas às regras (arquivo YAML) ou confirme que não entram no orçamento.",
                )
            )
        p += self._duplicadas(medidas_por_item)
        p += self._comprimento_zero(medidas_por_item)
        p += self._area_texto(desenho, medidas_por_item, itens_area_rotulada)
        p += self._blocos_aninhados(desenho)
        return p, nao_classificadas

    def _unidade(self, d: Desenho) -> list[Pendencia]:
        if d.fator_m is None:
            return [
                Pendencia(
                    disciplina=DISCIPLINA,
                    severidade=Severidade.BLOQUEANTE,
                    mensagem=(
                        f"O desenho não declara unidade ($INSUNITS = {d.insunits}). Comprimentos e áreas "
                        "não foram convertidos para metro."
                    ),
                    acao_sugerida="Confira uma cota conhecida e rode novamente com --unidade mm|cm|m.",
                )
            ]
        if d.origem_unidade == "informada pelo usuário":
            return [
                Pendencia(
                    disciplina=DISCIPLINA,
                    severidade=Severidade.INFO,
                    mensagem=f"Unidade '{d.unidade}' informada pelo usuário (cabeçalho: $INSUNITS = {d.insunits}).",
                )
            ]
        return []

    def _vazio(self, d: Desenho) -> list[Pendencia]:
        if not any(e.tipo in TIPOS_LINEARES or e.tipo == "INSERT" for e in d.entidades):
            return [
                Pendencia(
                    disciplina=DISCIPLINA,
                    severidade=Severidade.BLOQUEANTE,
                    mensagem="Espaço do modelo sem geometria. O desenho pode estar só no layout (paper space) ou em XREF.",
                    acao_sugerida="Use BIND nas referências externas e confirme que o projeto está no model space.",
                )
            ]
        return []

    def _nao_classificadas(self, d: Desenho, usadas: set[str]) -> dict[str, int]:
        cont: Counter[str] = Counter()
        for e in d.entidades:
            if e.tipo in TIPOS_TEXTO or e.tipo == "DIMENSION":
                continue
            if e.camada in usadas or self.regras.ignorada(e.camada):
                continue
            cont[e.camada] += 1
        return dict(cont)

    def _duplicadas(self, medidas: dict[str, list[Entidade]]) -> list[Pendencia]:
        out = []
        for codigo, ents in medidas.items():
            vistos: dict[tuple, str] = {}
            dup: list[str] = []
            for e in ents:
                if e.tipo == "INSERT":
                    chave = (e.bloco, round(e.insercao[0], 3), round(e.insercao[1], 3))
                elif e.pontos:
                    chave = assinatura(e.pontos)
                else:
                    continue
                if chave in vistos:
                    dup.append(e.handle)
                else:
                    vistos[chave] = e.handle
            if dup:
                out.append(
                    Pendencia(
                        disciplina=DISCIPLINA,
                        severidade=Severidade.ALERTA,
                        mensagem=f"{codigo}: {len(dup)} elemento(s) sobreposto(s)/duplicado(s) entraram na soma.",
                        handles=dup[:50],
                        acao_sugerida="Rode OVERKILL no CAD ou exclua as duplicatas e reprocesse.",
                    )
                )
        return out

    def _comprimento_zero(self, medidas: dict[str, list[Entidade]]) -> list[Pendencia]:
        zero = [e.handle for ents in medidas.values() for e in ents if e.tipo in TIPOS_LINEARES and e.comprimento == 0]
        if not zero:
            return []
        return [
            Pendencia(
                disciplina=DISCIPLINA,
                severidade=Severidade.INFO,
                mensagem=f"{len(zero)} entidade(s) de comprimento zero nas camadas medidas.",
                handles=zero[:50],
            )
        ]

    def _area_texto(
        self, d: Desenho, medidas: dict[str, list[Entidade]], codigos: set[str]
    ) -> list[Pendencia]:
        """Compara a área escrita no desenho (ex.: '12,50 m²') com a área do contorno."""
        if not d.fator_m:
            return []
        textos = [t for t in d.entidades if t.tipo in TIPOS_TEXTO and t.texto and t.insercao]
        out = []
        for codigo in codigos:
            for poli in medidas.get(codigo, []):
                for t in textos:
                    m = RX_AREA_TEXTO.search(t.texto)
                    if not m or not ponto_no_poligono(t.insercao, poli.pontos):
                        continue
                    escrita = float(m.group(1).replace(",", "."))
                    medida = poli.area * d.fator_m**2
                    if escrita > 0 and abs(medida - escrita) / escrita > TOLERANCIA_AREA:
                        out.append(
                            Pendencia(
                                disciplina=DISCIPLINA,
                                severidade=Severidade.ALERTA,
                                mensagem=(
                                    f"{codigo}: área escrita '{t.texto.strip()}' difere da área do contorno "
                                    f"({_virgula(medida)} m², diferença de {abs(medida - escrita) / escrita:.0%})."
                                ),
                                camada=poli.camada,
                                handles=[poli.handle, t.handle],
                                acao_sugerida="Confira o contorno do ambiente e o texto de área no projeto.",
                            )
                        )
        return out

    def _blocos_aninhados(self, d: Desenho) -> list[Pendencia]:
        por_camada: dict[str, set[str]] = defaultdict(set)
        for e in d.entidades:
            if e.tipo == "INSERT" and e.camada == "0":
                por_camada[e.camada].add(e.bloco or "?")
        if not por_camada:
            return []
        return [
            Pendencia(
                disciplina=DISCIPLINA,
                severidade=Severidade.INFO,
                mensagem="Há blocos inseridos na camada 0; eles não são classificados por disciplina.",
                camada="0",
                acao_sugerida="Mova os blocos para a camada da disciplina correspondente.",
            )
        ]
