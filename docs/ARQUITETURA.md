# Arquitetura do Quantum

## Fluxo dos agentes

```
 DWG ──(ODA File Converter)──┐
                             ▼
 DXF ──────────────► [1] Agente de ingestão  ── unidades ($INSUNITS), entidades normalizadas
                             │
          ┌──────────────────┼───────────────────┬───────────────────┐
          ▼                  ▼                   ▼                   ▼
 [2] Layout/Arquitetura  [3] Estrutural    [4] Elétrica       [5] Hidráulica
          └──────────────────┴─────────┬─────────┴───────────────────┘
                                       ▼
                         [6] Agente auditor ── pendências e inconsistências
                                       ▼
                         [7] Agente orçamentista ── tabela de preços do usuário (opcional)
                                       ▼
                         [8] Relatório ── Markdown · Excel · JSON
```

| # | Módulo | Responsabilidade |
|---|---|---|
| 1 | `ingestao.py` | Abre DXF (ezdxf) ou DWG (ODA), lê unidades, discretiza arcos/splines, calcula comprimento e área |
| 2–5 | `agentes/disciplina.py` + `regras_padrao.yaml` | Um agente por disciplina, guiado por regras de camada/bloco em YAML |
| 6 | `agentes/auditor.py` | Unidade, camadas sem regra, contornos abertos, duplicatas, área escrita × medida, model space vazio |
| 7 | `agentes/orcamentista.py` | Cruza quantitativos com a tabela CSV; confere unidade, fonte e data-base |
| 8 | `relatorio.py` | Saídas com o aviso de estimativa em todas |
| — | `orquestrador.py` | Coordena a ordem dos agentes |

## Decisões

1. **Agentes determinísticos primeiro.** Medir geometria é cálculo, não opinião. A IA (LLM) entra
   depois e só para *sugerir* (ex.: a que disciplina pertence uma camada de nome estranho),
   nunca para gerar número de quantitativo. O usuário confirma a sugestão, que vira regra no YAML.
2. **Regras em YAML, não no código.** Cada escritório tem seu padrão de layers. O padrão do
   cliente vira um arquivo de regras versionável.
3. **Parâmetro faltante é pendência, não valor padrão.** Pé-direito, altura de pilar, espessura
   de laje e BDI só entram quando o usuário informa.
4. **Rastreabilidade por handle.** Permite, numa próxima versão, destacar no desenho as
   entidades de cada item para conferência.

## Próximos passos sugeridos

- [ ] Agente de IA (Claude) para sugerir classificação das camadas não classificadas.
- [ ] Medir geometria dentro de blocos (explodir virtualmente) sem contar símbolos duas vezes.
- [ ] Área de hachuras e desconto de vãos na alvenaria.
- [ ] Linha dupla de parede/viga → comprimento de eixo.
- [ ] Prumadas e descidas a partir de parâmetros de altura por ponto.
- [ ] Importador de tabelas SINAPI/SEINFRA-CE (planilhas oficiais) para o CSV do Quantum.
- [ ] DXF de saída com os itens destacados por cor, para revisão visual.
- [ ] Interface web simples (upload do DXF → relatório).
