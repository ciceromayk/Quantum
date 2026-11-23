"""Agente de ingestão: abre DWG/DXF e normaliza as entidades do espaço do modelo.

- DXF é lido diretamente com `ezdxf`.
- DWG é convertido em memória pelo ODA File Converter (gratuito, instalado à parte),
  através de `ezdxf.addons.odafc`. Sem ele, o usuário recebe uma mensagem clara.
- Unidades vêm do cabeçalho `$INSUNITS`. Se o desenho não declara unidade, o Quantum
  NÃO adivinha: as medidas ficam em "unidades do desenho" e o auditor gera uma
  pendência bloqueante, a menos que o usuário informe a unidade.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf import path as ezpath

from .geometria import area_poligono, comprimento_pontos
from .modelos import Desenho, Entidade

# $INSUNITS -> (nome, fator para metro). Só unidades usuais em obra.
UNIDADES: dict[int, tuple[str, float]] = {
    4: ("mm", 0.001),
    5: ("cm", 0.01),
    6: ("m", 1.0),
    14: ("dm", 0.1),
}
FATOR_POR_NOME = {nome: fator for nome, fator in UNIDADES.values()}

TIPOS_LINEARES = {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"}
TIPOS_TEXTO = {"TEXT", "MTEXT"}


class ErroIngestao(RuntimeError):
    pass


def abrir_documento(caminho: str | Path):
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroIngestao(f"Arquivo não encontrado: {caminho}")
    sufixo = caminho.suffix.lower()
    if sufixo == ".dxf":
        try:
            return ezdxf.readfile(caminho)
        except ezdxf.DXFStructureError as exc:
            raise ErroIngestao(f"DXF inválido ou corrompido: {exc}") from exc
    if sufixo == ".dwg":
        from ezdxf.addons import odafc

        if not odafc.is_installed():
            raise ErroIngestao(
                "Para ler DWG é preciso instalar o ODA File Converter (gratuito): "
                "https://www.opendesign.com/guestfiles/oda_file_converter . "
                "Alternativa: exporte o arquivo como DXF no AutoCAD/BricsCAD/ZWCAD."
            )
        return odafc.readfile(str(caminho))
    raise ErroIngestao(f"Formato não suportado: {sufixo} (use .dxf ou .dwg)")


def _pontos_de(entidade, tolerancia: float) -> list[tuple[float, float]]:
    p = ezpath.make_path(entidade)
    return [(v.x, v.y) for v in p.flattening(distance=tolerancia)]


def _normalizar(e, tolerancia: float) -> Entidade | None:
    tipo = e.dxftype()
    camada = e.dxf.get("layer", "0")
    handle = e.dxf.get("handle", "")

    if tipo in TIPOS_LINEARES:
        try:
            pontos = _pontos_de(e, tolerancia)
        except (TypeError, ValueError):
            return None
        fechada = tipo in {"CIRCLE"} or bool(getattr(e, "closed", False)) or (
            tipo == "POLYLINE" and e.is_closed
        )
        if tipo == "ELLIPSE" and abs(e.dxf.end_param - e.dxf.start_param) >= 6.283:
            fechada = True
        if fechada and pontos and pontos[0] != pontos[-1]:
            pontos.append(pontos[0])
        return Entidade(
            handle=handle,
            tipo=tipo,
            camada=camada,
            pontos=pontos,
            fechada=fechada,
            comprimento=comprimento_pontos(pontos),
            area=area_poligono(pontos) if fechada else 0.0,
        )
    if tipo == "INSERT":
        ins = e.dxf.insert
        return Entidade(
            handle=handle, tipo=tipo, camada=camada, bloco=e.dxf.name, insercao=(ins.x, ins.y)
        )
    if tipo in TIPOS_TEXTO:
        ins = e.dxf.insert
        texto = e.plain_text() if tipo == "MTEXT" else e.dxf.text
        return Entidade(handle=handle, tipo=tipo, camada=camada, texto=texto, insercao=(ins.x, ins.y))
    # HATCH, DIMENSION etc. entram só no inventário de camadas
    return Entidade(handle=handle, tipo=tipo, camada=camada)


def carregar(caminho: str | Path, unidade: str | None = None) -> Desenho:
    """Lê o arquivo e devolve o `Desenho` normalizado.

    `unidade`: "mm", "cm", "dm" ou "m" para sobrepor o cabeçalho (use só quando
    tiver certeza, por exemplo conferindo uma cota conhecida).
    """
    doc = abrir_documento(caminho)
    insunits = int(doc.header.get("$INSUNITS", 0))

    if unidade:
        if unidade not in FATOR_POR_NOME:
            raise ErroIngestao(f"Unidade inválida: {unidade}. Use mm, cm, dm ou m.")
        nome, fator, origem = unidade, FATOR_POR_NOME[unidade], "informada pelo usuário"
    elif insunits in UNIDADES:
        nome, fator = UNIDADES[insunits]
        origem = "cabeçalho $INSUNITS"
    else:
        nome, fator, origem = None, None, "desconhecida"

    # Tolerância de discretização de arcos: 1 mm no mundo real, quando a unidade é conhecida.
    tolerancia = 0.001 / fator if fator else 0.01

    msp = doc.modelspace()
    entidades = [n for e in msp if (n := _normalizar(e, tolerancia)) is not None]
    camadas = sorted({layer.dxf.name for layer in doc.layers})

    return Desenho(
        arquivo=str(caminho),
        versao_dxf=doc.dxfversion,
        insunits=insunits,
        unidade=nome,
        fator_m=fator,
        entidades=entidades,
        camadas=camadas,
        origem_unidade=origem,
    )
