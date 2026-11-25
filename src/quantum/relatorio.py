"""Saídas do relatório: Markdown, JSON e Excel (.xlsx)."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .modelos import Relatorio, Severidade

ORDEM_SEV = {Severidade.BLOQUEANTE: 0, Severidade.ALERTA: 1, Severidade.INFO: 2}


def _fmt(v: float | None, casas: int = 2) -> str:
    if v is None:
        return "—"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _brl(v: float) -> str:
    return "R$ " + _fmt(v)


def para_markdown(rel: Relatorio) -> str:
    d = rel.desenho
    L = [
        "# Quantum · Levantamento de quantitativos",
        "",
        f"> ⚠️ {rel.aviso}",
        "",
        "## Arquivo",
        f"- Arquivo: `{Path(d.arquivo).name}` (DXF {d.versao_dxf})",
        f"- Unidade: {d.unidade or 'DESCONHECIDA'} ({d.origem_unidade})",
        f"- Entidades no espaço do modelo: {len(d.entidades)}",
    ]
    if rel.parametros:
        L.append("- Parâmetros informados: " + ", ".join(f"{k} = {v}" + ("" if isinstance(v, str) else " m") for k, v in rel.parametros.items()))

    pend = sorted(rel.pendencias, key=lambda p: ORDEM_SEV[p.severidade])
    n_bloq = sum(p.severidade == Severidade.BLOQUEANTE for p in pend)
    L += ["", f"## Pendências e inconsistências ({len(pend)}, {n_bloq} bloqueante(s))", ""]
    if not pend:
        L.append("Nenhuma pendência encontrada pelo auditor automático (a revisão humana continua obrigatória).")
    for p in pend:
        linha = f"- **{p.severidade.value.upper()}** · {p.disciplina}: {p.mensagem}"
        if p.camada:
            linha += f" _(camada: {p.camada})_"
        if p.acao_sugerida:
            linha += f"  \n  → {p.acao_sugerida}"
        L.append(linha)

    disciplinas: dict[str, list] = {}
    for i in rel.itens:
        disciplinas.setdefault(i.disciplina, []).append(i)
    L += ["", "## Quantitativos por disciplina", "",
          "Quantidades líquidas, sem perdas: nenhum percentual de perda ou quebra é aplicado."]
    if not disciplinas:
        L += ["", "Nenhum item encontrado. Verifique se os nomes de camada seguem as regras (`--regras`)."]
    for disc, itens in disciplinas.items():
        L += ["", f"### {disc}", "", "| Código | Descrição | Detalhe | Qtd. | Un. | Camadas | Observação |", "|---|---|---|---:|---|---|---|"]
        for i in itens:
            L.append(
                f"| {i.codigo} | {i.descricao} | {i.detalhe or ''} | {_fmt(i.quantidade)} | {i.unidade} "
                f"| {', '.join(i.camadas)} | {i.observacao or ''} |"
            )

    paredes = (rel.acabamentos or {}).get("alturas_parede") or []
    if paredes:
        L += ["", "### Revestimento de parede por ambiente", "",
              "Altura usada em cada ambiente e vãos descontados (só os acima de 2 m²).", "",
              "| Ambiente | Parede | Altura (m) | Origem da altura | Perímetro (m) | Bruta (m²) | Vãos descontados (m²) | Líquida (m²) |",
              "|---|---|---:|---|---:|---:|---:|---:|"]
        for a in paredes:
            L.append(
                f"| {a['nome']} | {a['codigo']} | {_fmt(a['altura_m'])} | {a['origem_altura'] or 'não informada'} "
                f"| {_fmt(a['perimetro_m'])} | {_fmt(a['area_bruta_m2'])} | {_fmt(a['desconto_vaos_m2'])} | {_fmt(a['area_liquida_m2'])} |"
            )

    if rel.orcamento:
        L += ["", "## Orçamento (estimativa)", "", "| Item | Ref. | Descrição | Qtd. | Un. | Preço unit. | Total | Fonte / data-base |", "|---|---|---|---:|---|---:|---:|---|"]
        for o in rel.orcamento:
            L.append(
                f"| {o.codigo_quantum} | {o.codigo_ref} | {o.descricao} | {_fmt(o.quantidade)} | {o.unidade} "
                f"| {_brl(o.preco_unitario)} | {_brl(o.total)} | {o.fonte} / {o.data_base} |"
            )
        L += ["", f"**Custo direto estimado: {_brl(rel.total_orcamento)}**"]
        if rel.bdi is not None:
            L.append(f"**Com BDI de {_fmt(rel.bdi)}% (informado): {_brl(rel.total_orcamento * (1 + rel.bdi / 100))}**")
        else:
            L.append("BDI não informado (use `--bdi`).")

    L += ["", "---", f"_{rel.aviso}_", ""]
    return "\n".join(L)


def para_dict(rel: Relatorio) -> dict:
    dados = asdict(rel)
    dados["desenho"].pop("entidades")
    dados["desenho"]["total_entidades"] = len(rel.desenho.entidades)
    dados["total_orcamento"] = rel.total_orcamento
    return dados


def para_json(rel: Relatorio) -> str:
    return json.dumps(para_dict(rel), ensure_ascii=False, indent=2, default=str)


def para_xlsx(rel: Relatorio, caminho: str | Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Leia-me"
    ws.append(["Quantum · Levantamento de quantitativos"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([rel.aviso])
    ws.append([])
    ws.append(["Arquivo", Path(rel.desenho.arquivo).name])
    ws.append(["Unidade", rel.desenho.unidade or "DESCONHECIDA", rel.desenho.origem_unidade])
    for k, v in rel.parametros.items():
        ws.append([f"Parâmetro {k}" + ("" if isinstance(v, str) else " (m)"), v])

    ws.append(["Quantidades líquidas, sem perdas: nenhum percentual de perda ou quebra é aplicado."])

    q = wb.create_sheet("Quantitativos")
    q.append(["Disciplina", "Código", "Descrição", "Detalhe", "Quantidade", "Unidade", "Camadas", "Observação"])
    for i in rel.itens:
        q.append([i.disciplina, i.codigo, i.descricao, i.detalhe, i.quantidade, i.unidade, ", ".join(i.camadas), i.observacao])

    p = wb.create_sheet("Pendências")
    p.append(["Severidade", "Disciplina", "Mensagem", "Camada", "Ação sugerida", "Handles"])
    for x in sorted(rel.pendencias, key=lambda p: ORDEM_SEV[p.severidade]):
        p.append([x.severidade.value, x.disciplina, x.mensagem, x.camada, x.acao_sugerida, " ".join(x.handles)])

    if rel.orcamento:
        o = wb.create_sheet("Orçamento")
        o.append(["Item Quantum", "Ref.", "Descrição", "Quantidade", "Unidade", "Preço unitário", "Total", "Fonte", "Data-base"])
        for n, x in enumerate(rel.orcamento, start=2):
            o.append([x.codigo_quantum, x.codigo_ref, x.descricao, x.quantidade, x.unidade, x.preco_unitario, f"=D{n}*F{n}", x.fonte, x.data_base])
        fim = len(rel.orcamento) + 1
        o.append([])
        o.append(["Custo direto", None, None, None, None, None, f"=SUM(G2:G{fim})"])
        if rel.bdi is not None:
            o.append(["BDI (%)", None, None, None, None, rel.bdi, f"=G{fim + 2}*(1+F{fim + 3}/100)"])

    if rel.acabamentos.get("ambientes"):
        a = wb.create_sheet("Acabamentos")
        a.append(["Ambiente", "Área rótulo (m²)", "Piso", "Parede", "Teto", "Área contorno (m²)", "Perímetro (m)"])
        for x in rel.acabamentos["ambientes"]:
            c = x["codigos"]
            a.append([x["nome"], x["area_rotulo"], c.get("piso"), c.get("parede"), c.get("teto"), x["area_contorno_m2"], x["perimetro_m"]])
        a.append([])
        a.append([rel.acabamentos.get("aviso_alturas", "")])

    if rel.acabamentos.get("alturas_parede"):
        w = wb.create_sheet("Paredes por ambiente")
        w.append(["Ambiente", "Parede", "Altura (m)", "Origem da altura", "Perímetro (m)", "Área bruta (m²)",
                  "Vãos descontados (m²)", "Área líquida (m²)", "Vãos (tipo_largura cm: situação)"])
        for x in rel.acabamentos["alturas_parede"]:
            vaos = "; ".join(f"{v['chave']}: {v['situacao'] or 'sem altura do ambiente'}" for v in x["vaos"])
            w.append([x["nome"], x["codigo"], x["altura_m"], x["origem_altura"] or "não informada", x["perimetro_m"],
                      x["area_bruta_m2"], x["desconto_vaos_m2"], x["area_liquida_m2"], vaos])
        w.append([])
        w.append(["Só vãos de porta e janela com área acima de 2 m² são descontados. Sem perdas."])

    if rel.paineis.get("linhas"):
        _folhas_paineis(wb, rel)

    for folha in wb.worksheets[1:]:
        for c in folha[1]:
            c.font = Font(bold=True)
        folha.freeze_panes = "A2"
    wb.save(caminho)


COLUNAS_PAINEIS = [
    "PROJETO REFERÊNCIA", "PLANTA FALADA", "LOCAL", "TIPO DE APARTAMENTO", "PAVIMENTO", "AMBIENTE",
    "CLASSIFICAÇÃO P/ LANÇAMENTO", "ESPECIFICAÇÃO", "REP (X)", "QTDE", "PERÍMETRO (M)",
    "ALTURA PÉ ESQUERDO (PISO A PISO) (M)", "ALTURA CONTRAPISO (M)", "ELEMENTO ESTRUTURAL",
    "ALTURA DO ELEMENTO ESTRUTURAL (LAJE OU VIGA) (M)", "ALTURA (M)", "ÁREA DA PAREDE (M2)", "ESQUADRIAS",
    "ÁREAS DE ESQUADRIAS (M2)", "ÁREA DE DESCONTOS (M2)", "ÁREA TOTAL (M2)", "MARCAÇÃO DRYWALL (M2)",
    "CHAPA ST (M2)", "CHAPA RU (M2)", "CHAPA GR (M2)", "CHAPA METÁLICA PARA REFORÇO (UND)",
    "ESTRUTURA METÁLICA DRYWALL DE 48MM (M2)", "ESTRUTURA METÁLICA DRYWALL DE 70MM (M2)",
    "ESTRUTURA METÁLICA STEEL FRAME 90MM (M2)", "ISOLAMENTO ACÚSTICO (M2)", "CANTONEIRA EM DRYWALL (M)",
    "MARCAÇÃO DE TIJOLO CERÂMICO (M)", "TIJOLO CERÂMICO 9CM (M2)", "TIJOLO CERÂMICO 14CM (M2)",
    "TIJOLO CERÂMICO 19CM (M2)", "MARCAÇÃO DE BLOCO DE CONCRETO (M)", "BLOCO DE CONCRETO DE 14CM",
]
# colunas somadas no Resumo (como a tabela dinâmica da planilha padrão)
RESUMO_PAINEIS = ["V", "AA", "AB", "AC", "Y", "X", "W", "AJ", "AK", "AF", "AG", "AH", "AI"]


def _folhas_paineis(wb, rel: Relatorio) -> None:
    """Planilha padrão de paredes e painéis, com as mesmas colunas e fórmulas do modelo do escritório."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    from .agentes.paineis import faces, perfil

    p = rel.paineis
    ws = wb.create_sheet("Paredes e Paineis")
    arq = Path(rel.desenho.arquivo).name
    ws.append(["QUANTITATIVO DE PAREDES E PAINÉIS - " + p.get("pavimento", "")])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([rel.aviso])
    ws.append(["Descontos: vãos com área maior que 2,00 m² descontam a área total. Sem perdas. Coluna e ambiente "
               "atribuídos automaticamente pela planta falada: confira."])
    cab = 5
    for i, t in enumerate(COLUNAS_PAINEIS, start=1):
        c = ws.cell(cab, i, t)
        c.font = Font(bold=True)
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.fill = PatternFill("solid", fgColor="DDEBF7")
    ws.row_dimensions[cab].height = 60
    r = cab
    for l in p["linhas"]:
        r += 1
        esp = l["especificacao"]
        fc = faces(esp)
        pf = perfil(esp)
        mult = lambda n: f"=U{r}*{n}" if n else 0
        cm = esp.split("DE ")[-1].replace("CM", "") if esp.startswith("ALVENARIA") else None
        valores = [
            "", arq, "", l["coluna"], l["pavimento"], l["ambiente"], l["classificacao"], esp, l["rep"], l["qtde"],
            l["perimetro_m"], l["pe_esquerdo"], l["contrapiso"], l["elemento"], l["altura_elemento"],
            f"=L{r}-M{r}-O{r}", f"=K{r}*P{r}", l["esquadrias"] or None, l["area_esquadrias_m2"], f"=S{r}",
            f"=I{r}*J{r}*(Q{r}-T{r})", f"=SUM(AA{r}:AC{r})",
            mult(fc.get("ST", 0)), mult(fc.get("RU", 0)), mult(fc.get("GR", 0)), None,
            f"=U{r}" if pf == "48" else None, f"=U{r}" if pf == "70" else None, f"=U{r}" if pf == "90" else None,
            None, None,
            f"=I{r}*J{r}*K{r}" if cm else None,
            f"=U{r}" if cm == "9" else None, f"=U{r}" if cm == "14" else None, f"=U{r}" if cm == "19" else None,
            f"=I{r}*J{r}*K{r}" if esp.startswith("BLOCO") else None, f"=U{r}" if esp.startswith("BLOCO") else None,
        ]
        for i, v in enumerate(valores, start=1):
            ws.cell(r, i, v)
    fim = r
    ws.freeze_panes = ws.cell(cab + 1, 9)
    for i in range(1, len(COLUNAS_PAINEIS) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 14
    for col in ("D", "F", "H", "R"):
        ws.column_dimensions[col].width = 26
    # quadro de esquadrias ao lado, como no modelo
    c0 = 42  # AP
    ws.cell(cab - 1, c0, "ESQUADRIAS (quadro informado)").font = Font(bold=True)
    for i, t in enumerate(["ID", "L (m)", "A (m)", "P (m)", "ÁREA (m²)", "DESCONTA? (> 2 m²)"]):
        ws.cell(cab, c0 + i, t).font = Font(bold=True)
    for k, e in enumerate(p.get("esquadrias", []), start=cab + 1):
        ws.cell(k, c0, e["id"])
        ws.cell(k, c0 + 1, e.get("largura"))
        ws.cell(k, c0 + 2, e.get("altura"))
        ws.cell(k, c0 + 3, e.get("peitoril"))
        L, A = get_column_letter(c0 + 1), get_column_letter(c0 + 2)
        ws.cell(k, c0 + 4, f'=IF(AND(ISNUMBER({L}{k}),ISNUMBER({A}{k})),{L}{k}*{A}{k},"")')
        ws.cell(k, c0 + 5, f'=IF(ISNUMBER({get_column_letter(c0 + 4)}{k}),IF({get_column_letter(c0 + 4)}{k}>2,"SIM","NÃO"),"falta no quadro")')

    rs = wb.create_sheet("Resumo Paredes")
    rs.append(["RESUMO - PAREDES E PAINÉIS - " + p.get("pavimento", "")])
    rs["A1"].font = Font(bold=True, size=13)
    rs.append([])
    nomes = {get_column_letter(i): t for i, t in enumerate(COLUNAS_PAINEIS, start=1)}
    rs.append(["Classificação"] + [nomes[c] for c in RESUMO_PAINEIS])
    for c in rs[3]:
        c.font = Font(bold=True)
        c.alignment = Alignment(wrap_text=True)
    rs.row_dimensions[3].height = 60
    lin = cab + 1
    for cla in sorted({l["classificacao"] for l in p["linhas"]}):
        k = rs.max_row + 1
        rs.cell(k, 1, cla)
        for j, c in enumerate(RESUMO_PAINEIS, start=2):
            rs.cell(k, j, f"=SUMIFS('Paredes e Paineis'!{c}{lin}:{c}{fim},'Paredes e Paineis'!G{lin}:G{fim},A{k})")
    k = rs.max_row + 1
    rs.cell(k, 1, "Total Geral").font = Font(bold=True)
    for j, c in enumerate(RESUMO_PAINEIS, start=2):
        rs.cell(k, j, f"=SUM('Paredes e Paineis'!{c}{lin}:{c}{fim})").font = Font(bold=True)
    rs.column_dimensions["A"].width = 22
    for j in range(2, len(RESUMO_PAINEIS) + 2):
        rs.column_dimensions[get_column_letter(j)].width = 16
