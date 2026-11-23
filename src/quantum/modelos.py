"""Modelos de dados compartilhados por todos os agentes do Quantum.

Todos os agentes leem um `Desenho` (representação neutra do DXF) e escrevem
`ItemQuantitativo` e `Pendencia` em um `Relatorio`. Nenhum agente altera o
arquivo original.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

AVISO_ESTIMATIVA = (
    "Os quantitativos e valores gerados pelo Quantum são ESTIMATIVAS TÉCNICAS "
    "extraídas automaticamente do desenho. Eles dependem da qualidade e da "
    "organização das camadas do arquivo e EXIGEM REVISÃO HUMANA por profissional "
    "habilitado, com conferência em projeto e em obra, antes de qualquer uso "
    "para compra, contratação ou medição."
)


class Medida(str, Enum):
    CONTAGEM = "contagem"  # unidades (blocos/INSERTs)
    COMPRIMENTO = "comprimento"  # m
    AREA = "area"  # m²


class Severidade(str, Enum):
    BLOQUEANTE = "bloqueante"  # impede o cálculo ou torna o número sem sentido
    ALERTA = "alerta"  # número calculado, mas precisa ser conferido
    INFO = "info"


@dataclass
class Entidade:
    """Entidade geométrica já normalizada a partir do DXF."""

    handle: str
    tipo: str  # LINE, LWPOLYLINE, INSERT, TEXT...
    camada: str
    pontos: list[tuple[float, float]] = field(default_factory=list)
    fechada: bool = False
    comprimento: float = 0.0  # unidades do desenho
    area: float = 0.0  # unidades do desenho ao quadrado (só se fechada)
    bloco: str | None = None  # nome do bloco (INSERT)
    texto: str | None = None  # conteúdo (TEXT/MTEXT)
    insercao: tuple[float, float] | None = None


@dataclass
class Desenho:
    arquivo: str
    versao_dxf: str
    insunits: int
    unidade: str | None  # "mm", "cm", "m" ou None se desconhecida
    fator_m: float | None  # multiplica unidades do desenho para obter metros
    entidades: list[Entidade]
    camadas: list[str]
    origem_unidade: str  # "cabeçalho $INSUNITS", "informada pelo usuário", "desconhecida"

    def por_camada(self) -> dict[str, list[Entidade]]:
        out: dict[str, list[Entidade]] = {}
        for e in self.entidades:
            out.setdefault(e.camada, []).append(e)
        return out


@dataclass
class Pendencia:
    disciplina: str
    severidade: Severidade
    mensagem: str
    camada: str | None = None
    handles: list[str] = field(default_factory=list)
    acao_sugerida: str | None = None


@dataclass
class ItemQuantitativo:
    disciplina: str
    codigo: str  # id do item na regra (ex.: ELE-TOMADAS)
    descricao: str
    unidade: str  # un, m, m², m³
    quantidade: float | None  # None = não calculável sem dado faltante
    camadas: list[str] = field(default_factory=list)
    detalhe: str | None = None  # ex.: nome do bloco ou do ambiente
    handles: list[str] = field(default_factory=list)  # rastreabilidade até a entidade
    observacao: str | None = None


@dataclass
class ItemOrcamento:
    codigo_quantum: str
    detalhe: str | None
    codigo_ref: str
    descricao: str
    unidade: str
    quantidade: float
    preco_unitario: float
    fonte: str
    data_base: str

    @property
    def total(self) -> float:
        return self.quantidade * self.preco_unitario


@dataclass
class Relatorio:
    desenho: Desenho
    itens: list[ItemQuantitativo] = field(default_factory=list)
    pendencias: list[Pendencia] = field(default_factory=list)
    orcamento: list[ItemOrcamento] = field(default_factory=list)
    bdi: float | None = None
    camadas_nao_classificadas: dict[str, int] = field(default_factory=dict)
    parametros: dict[str, float] = field(default_factory=dict)
    aviso: str = AVISO_ESTIMATIVA

    @property
    def total_orcamento(self) -> float:
        return sum(i.total for i in self.orcamento)
