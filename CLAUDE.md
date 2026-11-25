# Quantum: regras para quem mexe no código (pessoas e agentes)

O Quantum lê DXF/DWG de plantas e cortes de arquitetura e gera quantitativos de acabamentos, as
polilinhas de piso, forro e parede e um relatório. Roda inteiro no navegador (Pyodide num Web
Worker) e é publicado no GitHub Pages pelo `pages.yml` a cada push na `main`.

## 1. Evidência antes de dizer "pronto"

Nenhum PR é mesclado, e nenhuma correção é dada como feita, sem a verificação rodada **nesta
mudança** e com a saída lida. "Deve funcionar" ou "os testes passaram ontem" não contam.

| Afirmação | Exige |
|---|---|
| "Os testes passam" | `pytest -q` e `npm test` (em `web/`) com 0 falhas |
| "O app funciona" | `npm run verificar` com a planta e o corte reais (abaixo) terminando em `OK` |
| "O bug foi corrigido" | um teste que falhava antes da correção e passa depois |
| "A tela está certa" | captura de tela da verificação conferida, não só o código |

### Verificação no navegador (obrigatória antes do merge)

O pytest roda o Python do computador (GEOS 3.14). O site roda o Pyodide 0.27.2 (GEOS 3.12), em que
um erro de geometria derruba o motor e a tela trava. **Só o navegador mostra isso.** Por isso:

```bash
pip install -e ".[dev]"
scripts/preparar_navegador.sh                 # wheels Python do site
scripts/baixar_pyodide.sh                     # só se o ambiente não alcança o CDN jsDelivr
cd web && npm ci
VITE_PYODIDE_URL=./pyodide/ npm run build     # sem a variável, o site usa o CDN
npm run verificar -- \
  --planta  <planta do 1º pavimento tipo IDGP (15-IDGP-ARQ-EXE-1TPAC-R04.dxf)> \
  --corte   <corte 49-IDGP-ARQ-EXE-CRTAA-R01.dxf> \
  --alturas-do-corte --min-ambientes 56 --saida ../verificacao
```

- Os arquivos IDGP são de cliente: ficam na pasta do projeto, **nunca no Git** (`.gitignore`).
- Referência atual (25/11/2026): análise conclui em ~3 min com o corte de 287 MB, 56 de 61
  ambientes com contorno, alturas lidas do corte para COPA, COZ., LAVANDERIA e SALA/ESTAR.
  Se um desses números piorar, o PR não entra até explicar por quê.
- A verificação cria empreendimento e pavimento, envia corte e planta, espera a análise, abre
  todas as abas e falha se: a análise não concluir no prazo, o motor Python cair, a tela cair na
  barreira de erro ou ficar em branco, a planta não desenhar, faltar altura do corte, ou houver
  menos ambientes que o mínimo. Capturas e `resultado.json` ficam em `--saida`: olhe as capturas.
- No CI, o job `navegador` (`.github/workflows/testes.yml`) faz o mesmo caminho com a planta e o
  corte sintéticos de `scripts/amostras_navegador.py`. Ele não substitui a rodada com os arquivos
  reais, que é feita antes do merge.

## 2. Bug: primeiro o teste, depois a correção

1. Reproduza o problema e ache a causa (não o sintoma). Erro só no navegador se reproduz com
   `npm run verificar`.
2. Escreva o teste que falha (pytest para o Python; no navegador, um caso na verificação).
3. Corrija com a menor mudança que resolve a causa.
4. Rode o teste, a suíte e a verificação no navegador. Só então abra o PR.

Na detecção de ambientes, nada de `buffer`/overlay do shapely sem `grid_size`: o GEOS do Pyodide
aborta o processo (ver PR #19). O que dá para medir por distância é medido por distância.

## 3. Regras de quantitativo do usuário (não mudar sem ordem dele)

- **Nunca adivinhar dado técnico.** Sem unidade, pé-direito, altura de pilar, altura de vão etc.,
  o item fica sem quantidade e vira pendência com a ação sugerida.
- Vãos de portas e janelas: só os acima de 2 m² entram no desconto. Siga a regra como está
  implementada e documentada no código e no relatório; em caso de dúvida, pergunte ao usuário.
- **Sem perdas** em nenhum material.
- Altura de revestimento: vem dos cortes. Ambiente que não aparece no corte vira pendência, e o
  usuário preenche a altura (pé-direito menos a espessura da laje quando vai até o teto).
- Ler só o **Model** (pranchas e layouts são ignorados).
- Não há zonas nos projetos: o contorno dos ambientes é detectado pela geometria.
- O DXF de acabamentos é um arquivo novo; o arquivo do usuário nunca é regravado.
- Todo relatório e toda tela de resultado avisam que os números são estimativas técnicas e exigem
  revisão humana.

## 4. Interface

Telas novas ou alteradas seguem `docs/INTERFACE.md` (conferência lado a lado, estado por
extenso e não só por cor, erros que dizem o que fazer, números no padrão brasileiro).

## 5. Pull requests

- Branch a partir da `main` e PR pequeno.
- A descrição do PR diz o que foi verificado: cole o resumo `OK:` da verificação no navegador
  com os arquivos reais e os números de referência acima.
- Textos de tela, relatório e commits em português.
