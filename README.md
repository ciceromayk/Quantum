# Quantum

Levantamento de **quantitativos** e **orçamento** a partir de arquivos **DWG/DXF**, feito por um
grupo de agentes, um por disciplina: **Layout/Arquitetura, Estrutural, Elétrica e Hidráulica**.
Um agente auditor aponta inconsistências e dados faltantes **antes** de qualquer orçamento.

> ⚠️ Os números gerados são **estimativas técnicas** extraídas automaticamente do desenho.
> Eles dependem da organização das camadas do arquivo e **exigem revisão humana** por
> profissional habilitado, com conferência em projeto e em obra.

## Princípios

- **Não adivinhar dado técnico.** Sem unidade declarada, sem pé-direito ou sem altura de pilar,
  o item sai sem quantidade e vira **pendência**, com a ação sugerida.
- **Disciplinas separadas.** Cada disciplina tem seu agente e suas regras de camada.
- **Rastreabilidade.** Cada quantidade guarda os *handles* das entidades que a geraram.
- **Arquivo original intocado.** O Quantum só lê o desenho.
- **Preços vêm do usuário.** Nenhum preço é embutido. O orçamento usa uma tabela CSV com
  fonte e data-base (ex.: SINAPI ou SEINFRA-CE da data-base da obra, ou cotações).

## Instalação

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
```

Para ler **DWG** instale o [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)
(gratuito). Sem ele, exporte o projeto como DXF no seu CAD.

## Uso

```bash
quantum analisar projeto.dxf \
  --param pe_direito=2.80 --param altura_pilar=2.95 --param espessura_laje=0.12 \
  --precos minha_tabela.csv --bdi 25 \
  --saida saida/
```

Saídas em `saida/`: `projeto.md` (relatório), `projeto.xlsx` (abas Quantitativos, Pendências e
Orçamento com fórmulas) e `projeto.json`.

Opções úteis:

| Opção | Para quê |
|---|---|
| `--unidade mm\|cm\|m` | Desenho sem `$INSUNITS`. Confira uma cota conhecida antes de usar. |
| `--regras meu_padrao.yaml` | Padrão de camadas do seu escritório (copie `src/quantum/regras_padrao.yaml`). |
| `--disciplina eletrica` | Roda só uma ou algumas disciplinas. |
| `--param nome=valor` | Parâmetros em metros que o desenho 2D não contém. |

## O que a v0.1 mede

| Disciplina | Itens (regras padrão) |
|---|---|
| Layout | Área por ambiente (nome pelo texto dentro do contorno), área declarada nos rótulos de ambiente (blocos ou MTEXT com nome + "xx,xx m²"), esquadrias por tipo, comprimento de paredes, área de alvenaria (× pé-direito), portas e janelas (blocos) |
| Estrutural | Pilares (quantidade e área de seção), volume de pilares (× altura), comprimento de vigas, área e volume de lajes (× espessura) |
| Elétrica | Tomadas, interruptores, iluminação e quadros (blocos), eletrodutos em planta |
| Hidráulica | Água fria, água quente, esgoto e pluvial em planta, louças e metais (blocos) |

O auditor verifica: unidade do desenho, camadas sem disciplina, contornos abertos em camadas de
área, geometria duplicada (dupla contagem), área escrita no desenho × área do contorno,
espaço do modelo vazio (XREF/paper space) e blocos na camada 0.

## Arquivos exportados de BIM (ArchiCAD, Revit)

- Nomes de bloco por instância (`Vaso Sanitário 26[3]_1`) são agrupados pelo tipo (`Vaso Sanitário`).
- Blocos inseridos todos em (0,0), com a geometria em coordenadas do mundo, não são tratados como duplicatas.
- Zonas de ambiente costumam vir sem contorno: a área vem do rótulo e é marcada como "declarada", não medida.

## Limitações conhecidas (v0.1)

- Só o espaço do modelo. Geometria **dentro** de blocos e XREFs não é medida.
- Hachuras não entram na medição de área.
- Comprimentos de tubulação e eletroduto são **em planta**: sem prumadas, descidas e conexões.
- Paredes e vigas em linha dupla dão comprimento de faces, não de eixo.
- Não desconta vãos de portas e janelas da alvenaria.

## Sistema web (em construção)

A API está em `src/quantum_api` e a interface em `web/` ([docs/API.md](docs/API.md)):

```bash
pip install -e ".[api]"
(cd web && npm install && npm run build)  # interface
uvicorn quantum_api.main:app --reload     # http://127.0.0.1:8000
```

Arquitetura e próximos passos: [docs/ARQUITETURA.md](docs/ARQUITETURA.md).
Projetos estudados como referência e licenças: [docs/REFERENCIAS.md](docs/REFERENCIAS.md).
