"""Configuração por variáveis de ambiente (nada de segredo no código)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    database_url: str
    pasta_arquivos: Path
    tamanho_max_mb: int
    pasta_web: Path | None = None  # build da interface (web/dist)

    @classmethod
    def do_ambiente(cls) -> "Config":
        return cls(
            database_url=os.environ.get("QUANTUM_DATABASE_URL", "sqlite:///./dados/quantum.db"),
            pasta_arquivos=Path(os.environ.get("QUANTUM_PASTA_ARQUIVOS", "./dados/arquivos")),
            tamanho_max_mb=int(os.environ.get("QUANTUM_TAMANHO_MAX_MB", "200")),
            pasta_web=Path(os.environ.get("QUANTUM_PASTA_WEB", "./web/dist")),
        )
