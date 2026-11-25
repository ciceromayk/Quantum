# Diretrizes de interface do Quantum

Regras para as telas, principalmente as de **conferência**: aquelas em que o arquiteto compara o que
o Quantum leu do projeto com o que ele mediu, antes de usar qualquer número. Escritas para este
projeto, a partir das diretrizes de UX do
[ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) (licença MIT), filtradas
para uma ferramenta técnica de dados densos. Nada do pacote foi instalado.

## Conferência

1. **Lado a lado.** O valor do projeto (rótulo, etiqueta, corte) fica ao lado do valor medido, com a
   diferença calculada. Ninguém deve precisar fazer conta de cabeça.
2. **Problemas primeiro.** A lista abre filtrada em "A conferir" e ordenada por gravidade (sem
   contorno, área divergente, divisa proposta, confere). Quem conferiu tudo vê um estado vazio que
   diz isso com todas as letras.
3. **Estado por extenso, não só por cor.** Cada situação tem um selo com texto ("Sem contorno",
   "Área diverge") e uma dica ao passar o mouse. A cor só reforça (vermelho bloqueia, amarelo pede
   conferência, verde confere).
4. **A mesma regra do motor.** A tolerância mostrada na tela é a que o motor usa (5% na área do
   rótulo). Se a regra mudar no Python, muda aqui no mesmo PR.
5. **Caminho para ver o problema.** Toda linha suspeita aponta onde conferir (aba Planta, aba
   Parâmetros). Nada de diagnóstico sem próximo passo.
6. **Filtros com contagem.** Cada filtro mostra quantos itens tem; o filtro ativo fica marcado
   (`aria-pressed`) e a busca ignora acento.

## Números e tabelas

- Padrão brasileiro: vírgula decimal, duas casas para m² e m, `tabular-nums` para alinhar colunas.
- Números à direita, textos à esquerda; a unidade fica no cabeçalho da coluna, não repetida em cada
  célula.
- Diferenças com sinal (`+2,3%`, `−6,1%`).
- Tabelas largas rolam na horizontal dentro do cartão; a página nunca rola de lado.
- Cabeçalhos com `scope`; a primeira coluna (nome do ambiente) é cabeçalho de linha.

## Erros, avisos e estados

- Erro aparece perto de onde aconteceu, com `role="alert"`, dizendo o que houve e o que fazer.
  Nunca só "erro" ou um código.
- Erro não some sozinho: fica até a causa ser resolvida.
- Operação longa (conversão de DWG, leitura de corte, análise) mostra a etapa atual e não deixa
  repetir o envio enquanto roda.
- Estado vazio explica por que está vazio e o que fazer para preencher.
- Ação que apaga pede confirmação dizendo exatamente o que some.
- Toda tela de resultado mantém o aviso de que os números são estimativas técnicas e exigem
  revisão humana.

## Acessibilidade mínima

- Contraste de pelo menos 4,5:1 nos dois temas (claro e escuro), usando só as variáveis de cor de
  `estilo.css`.
- Foco visível (`:focus-visible`) em tudo que é clicável; caixas de seleção com pelo menos 16 px.
- Alvos de clique com pelo menos 24 px de altura (chips têm 32 px).
- Navegação por abas com `aria-current` na aba ativa.

## Como conferir uma tela nova

Rode `npm run verificar` (ver `CLAUDE.md`) e abra a captura da aba em `--saida`. A verificação abre
todas as abas, inclusive a Conferência, e falha se alguma cair na barreira de erro.
