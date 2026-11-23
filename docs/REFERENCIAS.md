# Projetos de referência

Estudados em 23/11/2026 como referência de arquitetura. **Nenhum código foi copiado** para o
Quantum; todo o código aqui é próprio.

## jeremylongshore/cad-ai-agent

- **Licença:** Apache-2.0 (permite uso comercial, com aviso de copyright e NOTICE se houver
  cópia de código).
- **O que é:** plataforma Python sobre `ezdxf` para editar e analisar DXF por linguagem natural
  (edição, compliance, saúde do desenho, takeoff, RFI, detecção de ambientes).
- **Leitura DWG:** converte com o ODA File Converter (`ezdxf.addons.odafc`), igual ao Quantum.
- **Ideias aproveitadas:** o LLM só devolve *planos estruturados* e nunca mexe no DXF; o
  takeoff é determinístico (contagem de blocos, comprimentos, áreas de contornos fechados);
  modo "mock" para rodar sem chave de API; arquivo original sempre preservado.
- **Diferenças do Quantum:** foco em orçamento brasileiro, separação por disciplina
  (layout/estrutural/elétrica/hidráulica), regras de camadas em YAML e auditor de pendências.

## A-SHOJAEI/ConstructDrawingAI

- **Licença:** PolyForm Noncommercial 1.0.0. **Uso comercial exige licença do autor.** Por isso
  o Quantum não usa nem adapta código deste projeto, só as ideias gerais abaixo, que são
  práticas comuns da área.
- **O que é:** visão computacional sobre desenhos (PDF/imagem/DXF/IFC): detecção de símbolos com
  modelos treinados, grafos de conectividade, takeoff, perguntas e respostas e RFI.
- **Ideias gerais:** uma representação intermediária única lida por todas as camadas; cada valor
  com nível de confiança e vínculo com a entidade de origem; itens de baixa confiança marcados
  para revisão humana.
- **Relevância futura:** útil se o Quantum passar a ler **PDF escaneado/imagem**. Nesse caso, os
  datasets e pesos têm licenças próprias (vários CC-BY-NC) e precisam de análise antes de uso
  comercial.
