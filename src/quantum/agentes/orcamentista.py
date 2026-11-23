"""Agente orçamentista: aplica uma tabela de preços FORNECIDA PELO USUÁRIO aos quantitativos.

O Quantum não embute preços. A tabela (CSV com ';') deve vir de uma fonte que o
usuário escolheu e datou, como composições SINAPI/SEINFRA-CE da data-base da obra
ou cotações de fornecedores. Formato em `exemplos/tabela_precos_modelo.csv`.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..modelos import ItemOrcamento, ItemQuantitativo, Pendencia, Severidade

DISCIPLINA = "Orçamento"
COLUNAS = ["item_quantum", "detalhe", "codigo_ref", "descricao", "unidade", "preco_unitario", "fonte", "data_base"]


def _num(txt: str) -> float:
    t = txt.strip().replace("R$", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    return float(t)


def _unid(u: str) -> str:
    return u.strip().lower().replace("m2", "m²").replace("m3", "m³").replace("und", "un").replace("unid", "un")


class AgenteOrcamentista:
    def __init__(self, tabela: str | Path):
        self.tabela = Path(tabela)

    def ler_tabela(self) -> list[dict]:
        with self.tabela.open(encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.DictReader(f, delimiter=";"))
        if linhas:
            faltam = [c for c in COLUNAS if c not in linhas[0]]
            if faltam:
                raise ValueError(f"Tabela de preços sem as colunas: {', '.join(faltam)}")
        return linhas

    def orcar(self, itens: list[ItemQuantitativo]) -> tuple[list[ItemOrcamento], list[Pendencia]]:
        orc: list[ItemOrcamento] = []
        pend: list[Pendencia] = []
        precificados: set[str] = set()

        for n, linha in enumerate(self.ler_tabela(), start=2):
            codigo = linha["item_quantum"].strip()
            if not codigo:
                continue
            detalhe = (linha.get("detalhe") or "").strip() or None
            candidatos = [i for i in itens if i.codigo == codigo]
            if detalhe:
                candidatos = [i for i in candidatos if i.detalhe == detalhe]
            elif any(i.detalhe == "total" for i in candidatos):
                candidatos = [i for i in candidatos if i.detalhe == "total"]
            if not candidatos:
                continue
            precificados.add(codigo)

            if not linha["preco_unitario"].strip():
                pend.append(self._p(Severidade.BLOQUEANTE, f"Linha {n} ({codigo}): preço unitário em branco."))
                continue
            try:
                preco = _num(linha["preco_unitario"])
            except ValueError:
                pend.append(self._p(Severidade.BLOQUEANTE, f"Linha {n} ({codigo}): preço inválido '{linha['preco_unitario']}'."))
                continue
            if not linha["fonte"].strip() or not linha["data_base"].strip():
                pend.append(
                    self._p(Severidade.ALERTA, f"Linha {n} ({codigo}): preço sem fonte ou sem data-base.")
                )
            unid_item = {_unid(i.unidade) for i in candidatos}
            if unid_item != {_unid(linha["unidade"])}:
                pend.append(
                    self._p(
                        Severidade.BLOQUEANTE,
                        f"Linha {n} ({codigo}): unidade da tabela '{linha['unidade']}' "
                        f"diferente da unidade do quantitativo '{', '.join(sorted(unid_item))}'.",
                    )
                )
                continue
            if any(i.quantidade is None for i in candidatos):
                pend.append(
                    self._p(Severidade.BLOQUEANTE, f"{codigo}: quantidade não calculada, item não orçado (ver pendências).")
                )
                continue
            orc.append(
                ItemOrcamento(
                    codigo_quantum=codigo,
                    detalhe=detalhe,
                    codigo_ref=linha["codigo_ref"].strip(),
                    descricao=linha["descricao"].strip(),
                    unidade=linha["unidade"].strip(),
                    quantidade=sum(i.quantidade for i in candidatos),
                    preco_unitario=preco,
                    fonte=linha["fonte"].strip(),
                    data_base=linha["data_base"].strip(),
                )
            )

        sem_preco = sorted({i.codigo for i in itens if i.quantidade} - precificados)
        if sem_preco:
            pend.append(
                self._p(
                    Severidade.INFO,
                    f"Itens com quantidade e sem preço na tabela: {', '.join(sem_preco)}.",
                )
            )
        return orc, pend

    @staticmethod
    def _p(sev: Severidade, msg: str) -> Pendencia:
        return Pendencia(disciplina=DISCIPLINA, severidade=sev, mensagem=msg)
