"""Formatos de entrada e saída da API (Pydantic)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Parâmetros que as regras padrão usam. Outros nomes são aceitos para regras próprias.
PARAMETROS_CONHECIDOS = {
    "pe_direito": "Pé-direito (m)",
    "altura_pilar": "Altura do lance de pilar (m)",
    "espessura_laje": "Espessura da laje (m)",
}


class ProjetoEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    endereco: str | None = Field(default=None, max_length=300)
    data_base: str | None = Field(default=None, max_length=20, description="Data-base do orçamento, ex.: 11/2026")


class PavimentoEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    repeticoes: int = Field(default=1, ge=1, le=200)


class Parametros(BaseModel):
    """Valores em metros que o desenho 2D não contém. Nunca há valor padrão."""

    valores: dict[str, float] = Field(default_factory=dict)
    unidade: Literal["mm", "cm", "dm", "m"] | None = None

    @field_validator("valores")
    @classmethod
    def _validar(cls, v: dict[str, float]) -> dict[str, float]:
        for nome, valor in v.items():
            if not nome.replace("_", "").isalnum() or len(nome) > 40:
                raise ValueError(f"nome de parâmetro inválido: {nome}")
            if not 0 < valor <= 100:
                raise ValueError(f"{nome} deve estar entre 0 e 100 metros")
        return v


class AnaliseResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    revisao: int
    arquivo_nome: str
    status: str
    erro: str | None
    criado_em: datetime
    concluido_em: datetime | None


class PavimentoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    projeto_id: int
    nome: str
    repeticoes: int
    parametros: dict
    unidade: str | None
    analises: list[AnaliseResumo] = []


class ProjetoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    endereco: str | None
    data_base: str | None
    criado_em: datetime
    pavimentos: list[PavimentoSaida] = []


class AnaliseDetalhe(AnaliseResumo):
    pavimento_id: int
    pendencias_por_severidade: dict[str, int] = {}
    resultado: dict | None = None
