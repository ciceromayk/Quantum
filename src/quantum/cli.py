"""Linha de comando: `quantum analisar projeto.dxf [opções]`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .ingestao import ErroIngestao
from .orquestrador import analisar
from .relatorio import para_json, para_markdown, para_xlsx


def _params(valores: list[str]) -> dict[str, float]:
    out = {}
    for v in valores or []:
        if "=" not in v:
            raise SystemExit(f"Parâmetro inválido '{v}'. Use nome=valor, ex.: pe_direito=2.80")
        k, x = v.split("=", 1)
        out[k.strip()] = float(x.replace(",", "."))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="quantum", description="Quantitativos e orçamento a partir de DWG/DXF.")
    sub = ap.add_subparsers(dest="comando", required=True)
    a = sub.add_parser("analisar", help="Levanta quantitativos de um arquivo DXF/DWG")
    a.add_argument("arquivo")
    a.add_argument("--regras", help="YAML de regras de camadas (padrão: regras_padrao.yaml do pacote)")
    a.add_argument("--unidade", choices=["mm", "cm", "dm", "m"], help="Sobrepõe o $INSUNITS do desenho")
    a.add_argument("--param", action="append", metavar="NOME=VALOR", help="Parâmetro em metros, ex.: pe_direito=2.80")
    a.add_argument("--precos", help="Tabela de preços CSV (;) para gerar o orçamento")
    a.add_argument("--bdi", type=float, help="BDI em %% (só se informado)")
    a.add_argument("--disciplina", action="append", help="Limita a disciplinas: layout, estrutural, eletrica, hidraulica")
    a.add_argument("--saida", default="saida", help="Pasta de saída (padrão: ./saida)")
    a.add_argument("--formatos", default="md,xlsx,json", help="md,xlsx,json")
    args = ap.parse_args(argv)

    try:
        rel = analisar(
            args.arquivo,
            regras=args.regras,
            unidade=args.unidade,
            parametros=_params(args.param),
            tabela_precos=args.precos,
            bdi=args.bdi,
            disciplinas=args.disciplina,
        )
    except (ErroIngestao, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    base = saida / Path(args.arquivo).stem
    formatos = {f.strip() for f in args.formatos.split(",")}
    md = para_markdown(rel)
    if "md" in formatos:
        base.with_suffix(".md").write_text(md, encoding="utf-8")
    if "json" in formatos:
        base.with_suffix(".json").write_text(para_json(rel), encoding="utf-8")
    if "xlsx" in formatos:
        para_xlsx(rel, base.with_suffix(".xlsx"))
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
