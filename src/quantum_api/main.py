"""Ponto de entrada do servidor: `uvicorn quantum_api.main:app`."""

from .app import criar_app

app = criar_app()
