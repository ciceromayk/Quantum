"""API web do Quantum (FastAPI): projetos, pavimentos, envio de DXF e resultados."""

from .app import criar_app

__all__ = ["criar_app"]
