"""Agente de disciplina: aplica as regras de UMA disciplina ao desenho.

Cada disciplina (layout, estrutural, elétrica, hidráulica) é uma instância deste
agente com regras próprias. O agente é determinístico: mede apenas o que está
desenhado e registra pendências quando falta informação.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .auditor import RX_AREA_TEXTO
from ..geometria import ponto_no_poligono, quase_fechada
from ..ingestao import TIPOS_LINEARES, TIPOS_TEXTO
from ..modelos import Desenho, Entidade, ItemQuantitativo, Medida, Pendencia, Severidade
from ..regras import RegraDisciplina, RegraItem


@dataclass
class ResultadoDisciplina:
    itens: list[ItemQuantitativo] = field(default_factory=list)
    pendencias: list[Pendencia] = field(default_factory=list)
    camadas_usadas: set[str] = field(default_factory=set)
    handles_medidos: dict[str, list[Entidade]] = field(default_factory=dict)  # codigo -> entidades


class AgenteDisciplina:
    def __init__(self, regra: RegraDisciplina, parametros: dict[str, float]):
        self.regra = regra
        self.parametros = parametros

    @property
    def nome(self) -> str:
        return self.regra.nome

    def executar(self, desenho: Desenho) -> ResultadoDisciplina:
        res = ResultadoDisciplina()
        textos = [e for e in desenho.entidades if e.tipo in TIPOS_TEXTO and e.texto]
        for item in self.regra.itens:
            casadas = [e for e in desenho.entidades if item.casa(e.camada, e.bloco)]
            if not casadas:
                continue
            res.camadas_usadas.update(e.camada for e in casadas)
            if item.medida == Medida.CONTAGEM:
                self._contagem(item, casadas, res)
            elif item.medida == Medida.COMPRIMENTO:
                self._comprimento(item, casadas, desenho, res)
            else:
                self._area(item, casadas, desenho, textos, res)
        return res

    # --- medidas -------------------------------------------------------------------

    def _contagem(self, item: RegraItem, casadas: list[Entidade], res: ResultadoDisciplina) -> None:
        blocos = [e for e in casadas if e.tipo == "INSERT"]
        por_bloco: dict[str, list[Entidade]] = defaultdict(list)
        for e in blocos:
            por_bloco[e.bloco or "?"].append(e)
        for nome_bloco, ents in sorted(por_bloco.items()):
            res.itens.append(
                ItemQuantitativo(
                    disciplina=self.nome,
                    codigo=item.codigo,
                    descricao=item.descricao,
                    unidade="un",
                    quantidade=float(len(ents)),
                    camadas=sorted({e.camada for e in ents}),
                    detalhe=f"bloco {nome_bloco}",
                    handles=[e.handle for e in ents],
                    observacao=item.observacao,
                )
            )
        res.handles_medidos[item.codigo] = blocos
        soltas = [e for e in casadas if e.tipo not in TIPOS_TEXTO and e.tipo != "INSERT"]
        if soltas:
            res.pendencias.append(
                Pendencia(
                    disciplina=self.nome,
                    severidade=Severidade.ALERTA,
                    mensagem=(
                        f"{item.codigo}: {len(soltas)} entidade(s) sem bloco nas camadas de contagem "
                        f"({', '.join(sorted({e.tipo for e in soltas}))}). "
                        "Símbolos desenhados sem bloco não são contados."
                    ),
                    camada=", ".join(sorted({e.camada for e in soltas})),
                    handles=[e.handle for e in soltas[:50]],
                    acao_sugerida="Converter os símbolos em blocos (BLOCK/INSERT) ou contar manualmente.",
                )
            )

    def _comprimento(
        self, item: RegraItem, casadas: list[Entidade], desenho: Desenho, res: ResultadoDisciplina
    ) -> None:
        lineares = [e for e in casadas if e.tipo in TIPOS_LINEARES]
        if not lineares:
            return
        res.handles_medidos[item.codigo] = lineares
        bruto = sum(e.comprimento for e in lineares)
        total = bruto * desenho.fator_m if desenho.fator_m else None
        obs = item.observacao
        if total is None:
            obs = _juntar(obs, f"Unidade do desenho desconhecida: {bruto:.3f} unidades do desenho.")
        res.itens.append(
            ItemQuantitativo(
                disciplina=self.nome,
                codigo=item.codigo,
                descricao=item.descricao,
                unidade="m",
                quantidade=total,
                camadas=sorted({e.camada for e in lineares}),
                handles=[e.handle for e in lineares],
                observacao=obs,
            )
        )
        self._derivados(item, total, res)

    def _area(
        self,
        item: RegraItem,
        casadas: list[Entidade],
        desenho: Desenho,
        textos: list[Entidade],
        res: ResultadoDisciplina,
    ) -> None:
        fechadas = [e for e in casadas if e.tipo in TIPOS_LINEARES and e.fechada and e.area > 0]
        abertas = [e for e in casadas if e.tipo in TIPOS_LINEARES and not e.fechada]
        hachuras = [e for e in casadas if e.tipo == "HATCH"]
        fator2 = desenho.fator_m**2 if desenho.fator_m else None
        res.handles_medidos[item.codigo] = fechadas

        if abertas:
            tol = 0.01 / desenho.fator_m if desenho.fator_m else 1e-6  # 1 cm
            quase = [e for e in abertas if quase_fechada(e.pontos, tol)]
            res.pendencias.append(
                Pendencia(
                    disciplina=self.nome,
                    severidade=Severidade.ALERTA,
                    mensagem=(
                        f"{item.codigo}: {len(abertas)} contorno(s) aberto(s) em camada de área não foram medidos"
                        + (f" ({len(quase)} parecem fechados mas não têm a propriedade 'fechada')." if quase else ".")
                    ),
                    camada=", ".join(sorted({e.camada for e in abertas})),
                    handles=[e.handle for e in abertas[:50]],
                    acao_sugerida="Fechar as polilinhas (PEDIT > Close) ou redesenhar com BOUNDARY.",
                )
            )
        if hachuras:
            res.pendencias.append(
                Pendencia(
                    disciplina=self.nome,
                    severidade=Severidade.INFO,
                    mensagem=f"{item.codigo}: {len(hachuras)} hachura(s) na camada não entram na medição (v0.1).",
                    camada=", ".join(sorted({e.camada for e in hachuras})),
                )
            )
        if not fechadas:
            return

        def m2(valor: float) -> float | None:
            return valor * fator2 if fator2 else None

        obs_unid = None if fator2 else "Unidade do desenho desconhecida."
        if item.rotular_por_texto:
            for e in fechadas:
                rotulo = _rotulo(e, textos)
                res.itens.append(
                    ItemQuantitativo(
                        disciplina=self.nome,
                        codigo=item.codigo,
                        descricao=item.descricao,
                        unidade="m²",
                        quantidade=m2(e.area),
                        camadas=[e.camada],
                        detalhe=rotulo or f"sem nome (handle {e.handle})",
                        handles=[e.handle],
                        observacao=_juntar(item.observacao, obs_unid),
                    )
                )
            sem_nome = [e for e in fechadas if not _rotulo(e, textos)]
            if sem_nome:
                res.pendencias.append(
                    Pendencia(
                        disciplina=self.nome,
                        severidade=Severidade.INFO,
                        mensagem=f"{item.codigo}: {len(sem_nome)} contorno(s) sem texto de nome dentro.",
                        handles=[e.handle for e in sem_nome],
                    )
                )
        total_bruto = sum(e.area for e in fechadas)
        total = m2(total_bruto)
        res.itens.append(
            ItemQuantitativo(
                disciplina=self.nome,
                codigo=item.codigo,
                descricao=f"{item.descricao} (total)",
                unidade="m²",
                quantidade=total,
                camadas=sorted({e.camada for e in fechadas}),
                detalhe="total",
                handles=[e.handle for e in fechadas],
                observacao=_juntar(item.observacao, obs_unid),
            )
        )
        if item.contar_elementos:
            res.itens.append(
                ItemQuantitativo(
                    disciplina=self.nome,
                    codigo=f"{item.codigo}-UN",
                    descricao=f"{item.descricao} (quantidade de elementos)",
                    unidade="un",
                    quantidade=float(len(fechadas)),
                    camadas=sorted({e.camada for e in fechadas}),
                    handles=[e.handle for e in fechadas],
                )
            )
        self._derivados(item, total, res)

    def _derivados(self, item: RegraItem, base: float | None, res: ResultadoDisciplina) -> None:
        for d in item.derivados:
            valor_param = self.parametros.get(d.parametro)
            if valor_param is None:
                res.pendencias.append(
                    Pendencia(
                        disciplina=self.nome,
                        severidade=Severidade.BLOQUEANTE,
                        mensagem=f"{d.codigo}: falta o parâmetro '{d.parametro}' (não consta no desenho 2D).",
                        acao_sugerida=f"Informe com --param {d.parametro}=<valor em metros>, conforme projeto.",
                    )
                )
            qtd = base * valor_param if (base is not None and valor_param is not None) else None
            res.itens.append(
                ItemQuantitativo(
                    disciplina=self.nome,
                    codigo=d.codigo,
                    descricao=d.descricao,
                    unidade=d.unidade,
                    quantidade=qtd,
                    observacao=(
                        f"{d.parametro} = {valor_param} m (informado pelo usuário)"
                        if valor_param is not None
                        else f"Aguardando parâmetro {d.parametro}."
                    ),
                )
            )


def _rotulo(poligono: Entidade, textos: list[Entidade]) -> str | None:
    dentro = [t.texto.strip() for t in textos if t.insercao and ponto_no_poligono(t.insercao, poligono.pontos)]
    dentro = [t for t in dentro if t and not RX_AREA_TEXTO.search(t)]
    return " / ".join(dentro[:2]) if dentro else None


def _juntar(*partes: str | None) -> str | None:
    p = [x for x in partes if x]
    return " ".join(p) if p else None
