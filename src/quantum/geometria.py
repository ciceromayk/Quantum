"""Funções geométricas puras (sem dependência de CAD)."""

from __future__ import annotations

import math

Ponto = tuple[float, float]


def comprimento_pontos(pontos: list[Ponto]) -> float:
    return sum(math.dist(a, b) for a, b in zip(pontos, pontos[1:]))


def area_poligono(pontos: list[Ponto]) -> float:
    """Área pela fórmula de Gauss (shoelace). Aceita polígono aberto ou fechado."""
    if len(pontos) < 3:
        return 0.0
    s = 0.0
    n = len(pontos)
    for i in range(n):
        x1, y1 = pontos[i]
        x2, y2 = pontos[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def ponto_no_poligono(p: Ponto, poligono: list[Ponto]) -> bool:
    """Ray casting. O polígono pode ou não repetir o primeiro ponto no fim."""
    x, y = p
    dentro = False
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cruz = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cruz:
                dentro = not dentro
    return dentro


def quase_fechada(pontos: list[Ponto], tolerancia: float) -> bool:
    """Polilinha aberta cujo último ponto coincide (dentro da tolerância) com o primeiro."""
    return len(pontos) >= 4 and math.dist(pontos[0], pontos[-1]) <= tolerancia


def assinatura(pontos: list[Ponto], casas: int = 3) -> tuple:
    """Chave para detectar geometria duplicada/sobreposta (independe do sentido)."""
    arred = tuple((round(x, casas), round(y, casas)) for x, y in pontos)
    return min(arred, tuple(reversed(arred)))
