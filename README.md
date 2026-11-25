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
  - o vão da esquadria é fechado pelas linhas de parede do próprio bloco (as faces e os
    batentes); a porta em si não vira barreira nem contorno;
  - linhas de projeção (`PROJ`) separam ambientes integrados; os pedaços são combinados até bater
    com as áreas dos rótulos;
  - dois ambientes no mesmo espaço sem linha entre eles recebem uma **divisa proposta** (reta que
    reparte a área na proporção dos rótulos), marcada como alerta e gravada em
    `QTD-xx-PROPOSTA` no DXF gerado;
  - nada é aceito se a área não bater com o rótulo (5%); o resto vira pendência. Divisas sem
    parede (projeção ou proposta) não entram no perímetro de parede.
- Parede = perímetro do contorno × altura do revestimento, menos, em cada vão de porta e
  janela, só a parte que **excede 2 m²** (critério TCPO/SINAPI; vão de até 2 m² entra cheio). Nenhuma perda é aplicada em material
  nenhum. A altura **não é presumida**: vem do corte, ou da altura do ambiente informada à mão
  (`altura_ambiente_<NOME>` em metros, ou `laje` para usar o pé-direito descontada a espessura da
  laje), ou de `altura_parede_<código>` (metros ou `laje`). Envie cortes com `--corte corte.dxf`;
  quando o corte não representa todos os ambientes da planta, um alerta lista os que faltam para
  preencher à mão. A altura e o peitoril das esquadrias não estão na planta: informe
  `altura_vao_<porta|janela>_<largura em cm>` e, nas janelas, `peitoril_vao_janela_<largura>`
  (a largura é medida no bloco). O desconto não passa da parte do vão dentro da faixa
  revestida. Vão que nem com a altura máxima (pé-direito − laje) passa de 2 m² dispensa a altura. No corte, o revestimento é a hachura de padrão GRELHA/cerâmica/porcelanato
  na parede vista; a altura vai do piso acabado até a laje ou forro cortado, e o ambiente é o nome
  escrito na faixa. **Alturas tiradas de cortes valem só para os ambientes cortados e precisam de
  conferência.** A altura do corte vale para o ambiente da planta com o mesmo nome e, quando
  nenhum nome é igual, para o que tem um pedaço de nome em comum (`COZ.` do corte vale para
  `COZ. / SERV.` da planta), só se todos os cortes parecidos derem a mesma altura — o que casou
  assim vira alerta para conferência. Se o mesmo nome aparece com alturas diferentes, nenhuma é
  usada. Trecho de revestimento sem nome de ambiente dentro da faixa não é adivinhado: vira
  alerta dizendo quantos são e com que alturas.
- A aba **Planta** mostra as polilinhas geradas junto com o desenho: cada acabamento entra como
  uma camada `QTD-*` própria, com a cor do DXF gerado, que se liga e desliga na lista de camadas
  (grupo "Acabamentos (geradas)"). É o mesmo desenho do arquivo que se baixa.
- Gera um **DXF novo** (`<arquivo>_acabamentos.dxf`), montado do zero em AutoCAD 2013 com uma
  cópia do Model. O original não é alterado. As polilinhas saem com 2,5 cm de espessura:
  - `QTD-PISO-xx` e `QTD-TETO-xx`: polilinha **fechada**, que é a área do ambiente. Ambientes
    **integrados** (contornos que se encostam, sem parede entre eles) com o **mesmo código** de
    piso ou de forro viram **uma polilinha só**, sem a divisa, e sem a marca `-PROPOSTA`: a área
    é contínua no desenho, embora o quantitativo continue somando ambiente por ambiente. Frestas
    de até 2 cm entre os dois contornos (a divisa proposta é reta, a parede vizinha nem sempre)
    são fechadas na união;
  - `QTD-PAREDE-xx`: polilinhas **abertas**, só nos trechos colados a uma parede (a divisa com o
    ambiente vizinho, por projeção ou proposta, não é parede e fica de fora).
  - Uma camada por acabamento, com o material no nome e uma cor própria, por exemplo
    `QTD-PISO-01 PORCELANATO ELIANE MUNARI MARFIM AC 60 x 60 cm`.
  - O contorno **segue reto na face da parede**: a porta (folha, arco de abertura), os batentes,
    os requadros de janela e os alisares não entram, e os cantos saem em esquadro. Um **degrau
    de parede** (ponta de alvenaria, viradinha) não é requadro: as duas faces são paralelas mas
    não estão no mesmo plano, então a virada fica no contorno e entra no perímetro de parede.

## Só o Model e visualizador

- O Quantum lê **só o Model** do arquivo. Pranchas (layouts/paper space) repetem o desenho em
  viewports e trazem carimbo e notas, que contariam em dobro; elas são ignoradas e a análise
  avisa quantas entidades ficaram de fora.
- A aba **Planta** da análise mostra o desenho do Model no navegador: camadas com as cores do
  arquivo (liga/desliga), textos, zoom e arrasto (mouse ou toque) e os contornos de ambiente
  detectados por cor (verde: detectado; azul: separado por projeção; laranja: divisa proposta).
  Clicar num ambiente mostra rótulo, área do contorno, perímetro de parede e códigos de acabamento.

## Arquivos exportados de BIM (ArchiCAD, Revit)

- Nomes de bloco por instância (`Vaso Sanitário 26[3]_1`) são agrupados pelo tipo (`Vaso Sanitário`).
- Blocos inseridos todos em (0,0), com a geometria em coordenadas do mundo, não são tratados como duplicatas.
- Zonas de ambiente costumam vir sem contorno: o contorno é detectado pela geometria (ver Acabamentos); onde não dá, a área vem do rótulo e é marcada como "declarada", não medida.

## Limitações conhecidas (v0.1)

- Só o espaço do modelo. Geometria **dentro** de blocos e XREFs não é medida.
- Hachuras não entram na medição de área.
- Comprimentos de tubulação e eletroduto são **em planta**: sem prumadas, descidas e conexões.
- Paredes e vigas em linha dupla dão comprimento de faces, não de eixo.
- Não desconta vãos de portas e janelas da alvenaria (só do revestimento de parede).

## Sistema web (GitHub Pages)

Endereço: **https://ciceromayk.github.io/Quantum/**

A interface em `web/` roda **inteira no navegador**: o mesmo núcleo Python é executado com
[Pyodide](https://pyodide.org) (Python em WebAssembly) dentro de um Web Worker. Não há servidor.

- Aceita **DXF** (texto ou binário), **DWG** e **.zip** com um desenho dentro. O formato é
  reconhecido pelo conteúdo. O DWG é convertido para DXF no próprio navegador pelo
  [LibreDWG](https://www.gnu.org/software/libredwg/) em WebAssembly (pacote
  [`@mlightcad/libredwg-web`](https://github.com/mlightcad/libredwg-web), GPL-3.0, carregado
  só quando chega um DWG, cerca de 10 MB uma vez). Versões aceitas: AutoCAD R13 a 2018+ (formato
  AC1032, usado até as versões atuais); anteriores são experimentais. Se uma versão não for lida, o
  site pede para exportar DXF. O Quantum **não grava DWG**: a saída continua sendo o DXF pequeno só
  com as camadas novas, para anexar como xref.
- O desenho **não sai do computador** de quem usa. Projetos, análises e relatórios ficam no
  IndexedDB daquele navegador.
- Para backup ou para levar a outro computador, use **Exportar** (gera um `.json` sem o DXF) e
  **Importar projeto**.
- A primeira análise baixa o Python (cerca de 15 MB, uma vez só, do CDN jsDelivr). O DXF de
  teste de 18 MB levou cerca de 20 s num computador comum.
- Arquivos de até 500 MB. Ficam guardados no disco do navegador e o Python lê direto deles, sem
  copiar o arquivo inteiro para a memória. Cortes são lidos em fluxo (só hachuras e textos): o
  corte de 287 MB do projeto usa cerca de 60 MB de memória. A planta precisa ser carregada
  inteira (blocos, portas, paredes) e usa por volta de 5 vezes o tamanho do arquivo: acima de
  ~150 MB pode faltar memória no navegador; nesse caso, exporte só o pavimento.
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
