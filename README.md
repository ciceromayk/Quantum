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

## Acabamentos (planta de acabamentos)

Quando o DXF é uma planta de acabamentos, o agente de acabamentos:

- Lê o **quadro de acabamentos** do próprio desenho (colunas "ESPECIFICAÇÃO - PISO/PAREDE/TETO/RODAPÉ").
- Lê a **etiqueta de cada ambiente**: bloco com 3 números. A posição de cada número diz se é piso,
  parede ou teto (padrão: em cima à esquerda = piso, em cima à direita = parede, embaixo à esquerda
  = teto). Ajuste em `acabamentos.etiqueta` nas regras se o seu escritório usar outra convenção.
- Soma piso e teto por código. Usa a área do contorno do ambiente quando existe uma polilinha
  fechada que bate com o rótulo; senão, usa a área declarada no rótulo e avisa.
- **Sem zonas, detecta o ambiente pela geometria** (`acabamentos.deteccao` nas regras):
  - as camadas de parede fecham o espaço (linhas duplas e folgas de 2 cm são unidas);
  - cada bloco de esquadria fecha o vão pela parte que fica dentro da parede, e o arco da porta
    vira folha fechada, para o espaço não vazar nem perder o giro da porta;
  - linhas de projeção (`PROJ`) separam ambientes integrados; os pedaços são combinados até bater
    com as áreas dos rótulos;
  - dois ambientes no mesmo espaço sem linha entre eles recebem uma **divisa proposta** (reta que
    reparte a área na proporção dos rótulos), marcada como alerta e gravada em
    `QTD-xx-PROPOSTA` no DXF gerado;
  - nada é aceito se a área não bater com o rótulo (5%); o resto vira pendência. Divisas sem
    parede (projeção ou proposta) não entram no perímetro de parede.
- Parede = perímetro do contorno × altura do revestimento. A altura **não é presumida**: informe
  `altura_parede_<código>` em metros, ou `teto` para usar o pé-direito, ou envie cortes com
  `--corte corte.dxf`. No corte, o revestimento é a hachura de padrão GRELHA/cerâmica/porcelanato
  na parede vista; a altura vai do piso acabado até a laje ou forro cortado, e o ambiente é o nome
  escrito na faixa. **Alturas tiradas de cortes valem só para os ambientes cortados e precisam de
  conferência.** A altura do corte vale para o ambiente da planta com o mesmo nome; se o mesmo
  nome aparece com alturas diferentes, nenhuma é usada.
- Gera um **DXF novo** (`<arquivo>_acabamentos.dxf`) com polilinhas fechadas nas camadas
  `QTD-PISO-xx`, `QTD-PAREDE-xx` e `QTD-TETO-xx`. O original não é alterado.

## Arquivos exportados de BIM (ArchiCAD, Revit)

- Nomes de bloco por instância (`Vaso Sanitário 26[3]_1`) são agrupados pelo tipo (`Vaso Sanitário`).
- Blocos inseridos todos em (0,0), com a geometria em coordenadas do mundo, não são tratados como duplicatas.
- Zonas de ambiente costumam vir sem contorno: o contorno é detectado pela geometria (ver Acabamentos); onde não dá, a área vem do rótulo e é marcada como "declarada", não medida.

## Limitações conhecidas (v0.1)

- Só o espaço do modelo. Geometria **dentro** de blocos e XREFs não é medida.
- Hachuras não entram na medição de área.
- Comprimentos de tubulação e eletroduto são **em planta**: sem prumadas, descidas e conexões.
- Paredes e vigas em linha dupla dão comprimento de faces, não de eixo.
- Não desconta vãos de portas e janelas da alvenaria.

## Sistema web (GitHub Pages)

Endereço: **https://ciceromayk.github.io/Quantum/**

A interface em `web/` roda **inteira no navegador**: o mesmo núcleo Python é executado com
[Pyodide](https://pyodide.org) (Python em WebAssembly) dentro de um Web Worker. Não há servidor.

- O DXF **não sai do computador** de quem usa. Projetos, análises e relatórios ficam no
  IndexedDB daquele navegador.
- Para backup ou para levar a outro computador, use **Exportar** (gera um `.json` sem o DXF) e
  **Importar projeto**.
- A primeira análise baixa o Python (cerca de 15 MB, uma vez só, do CDN jsDelivr). O DXF de
  teste de 18 MB levou cerca de 20 s num computador comum. Arquivos muito grandes podem ficar lentos.
- Cada push na `main` publica o site pelo workflow `.github/workflows/pages.yml`.

Rodar localmente:

```bash
scripts/preparar_navegador.sh             # gera as wheels Python em web/public/py
(cd web && npm install && npm run dev)    # http://localhost:5173
```

A API FastAPI em `src/quantum_api` ([docs/API.md](docs/API.md)) continua no repositório para uso
em servidor próprio, mas a interface publicada não depende dela.

Arquitetura e próximos passos: [docs/ARQUITETURA.md](docs/ARQUITETURA.md).
Projetos estudados como referência e licenças: [docs/REFERENCIAS.md](docs/REFERENCIAS.md).
