"""Carregamento e validação das regras (YAML) de camadas e itens."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

from .modelos import Medida

UNIDADE_POR_MEDIDA = {Medida.CONTAGEM: "un", Medida.COMPRIMENTO: "m", Medida.AREA: "m²", Medida.AREA_ROTULO: "m²"}


@dataclass
class Derivado:
    codigo: str
    descricao: str
    parametro: str
    unidade: str


@dataclass
class RegraItem:
    codigo: str
    descricao: str
    medida: Medida
    camadas: list[re.Pattern] = field(default_factory=list)
    blocos: list[re.Pattern] = field(default_factory=list)
    observacao: str | None = None
    derivados: list[Derivado] = field(default_factory=list)
    rotular_por_texto: bool = False
    contar_elementos: bool = False

    @property
    def unidade(self) -> str:
        return UNIDADE_POR_MEDIDA[self.medida]

    def casa_camada(self, camada: str) -> bool:
        return any(p.search(camada) for p in self.camadas)

    def casa(self, camada: str, bloco: str | None) -> bool:
        ok_camada = self.casa_camada(camada) if self.camadas else True
        ok_bloco = bool(bloco) and any(p.search(bloco) for p in self.blocos) if self.blocos else True
        return (bool(self.camadas) or bool(self.blocos)) and ok_camada and ok_bloco


@dataclass
class RegraDisciplina:
    chave: str
    nome: str
    itens: list[RegraItem]


@dataclass
class Regras:
    disciplinas: list[RegraDisciplina]
    ignorar: list[re.Pattern]
    origem: str

    def ignorada(self, camada: str) -> bool:
        return any(p.search(camada) for p in self.ignorar)


def _rx(lista) -> list[re.Pattern]:
    return [re.compile(s, re.IGNORECASE) for s in (lista or [])]


def caminho_padrao() -> Path:
    return Path(str(resources.files("quantum") / "regras_padrao.yaml"))


def carregar_regras(caminho: str | Path | None = None) -> Regras:
    caminho = Path(caminho) if caminho else caminho_padrao()
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    codigos: set[str] = set()
    disciplinas = []
    for chave, d in (dados.get("disciplinas") or {}).items():
        itens = []
        for i in d.get("itens", []):
            medida = Medida(i["medida"])
            if i["codigo"] in codigos:
                raise ValueError(f"Código de item repetido nas regras: {i['codigo']}")
            codigos.add(i["codigo"])
            if i.get("blocos") and medida not in (Medida.CONTAGEM, Medida.AREA_ROTULO):
                raise ValueError(f"{i['codigo']}: filtro 'blocos' só vale para contagem e area_rotulo")
            itens.append(
                RegraItem(
                    codigo=i["codigo"],
                    descricao=i["descricao"],
                    medida=medida,
                    camadas=_rx(i.get("camadas")),
                    blocos=_rx(i.get("blocos")),
                    observacao=i.get("observacao"),
                    derivados=[Derivado(**x) for x in i.get("derivados", [])],
                    rotular_por_texto=bool(i.get("rotular_por_texto")),
                    contar_elementos=bool(i.get("contar_elementos")),
                )
            )
        disciplinas.append(RegraDisciplina(chave=chave, nome=d.get("nome", chave), itens=itens))
    return Regras(disciplinas=disciplinas, ignorar=_rx(dados.get("ignorar_camadas")), origem=str(caminho))
