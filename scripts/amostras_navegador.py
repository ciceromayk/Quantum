"""Gera a planta e o corte sintéticos que a verificação no navegador usa no CI.

Os arquivos reais de cliente não vão para o Git; estes reproduzem o padrão deles (paredes duplas,
porta em bloco, integrados, divisa proposta, etiquetas de acabamento e corte com hachura GRELHA).

Uso: python scripts/amostras_navegador.py PASTA
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tests"))

from test_acabamentos import criar_corte  # noqa: E402
from test_ambientes import criar_planta  # noqa: E402

destino = Path(sys.argv[1] if len(sys.argv) > 1 else "amostras")
destino.mkdir(parents=True, exist_ok=True)
criar_planta(destino / "planta_sintetica.dxf")
criar_corte(destino / "corte_sintetico.dxf")
print(f"Amostras em {destino}/")
