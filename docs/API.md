# API do Quantum (etapa 1)

> A interface publicada no GitHub Pages roda no navegador e **não usa esta API**. Ela fica para quem quiser hospedar um servidor próprio (ex.: dados compartilhados pela equipe).

Servidor: `uvicorn quantum_api.main:app --reload` → interface em `/`, rotas sob `/api`, documentação interativa em `/docs`.

| Método | Rota | O que faz |
|---|---|---|
| GET | `/api/saude` | Versão e aviso de estimativa |
| GET | `/api/parametros-conhecidos` | Parâmetros usados pelas regras padrão |
| POST | `/api/projetos` | Cria empreendimento (`nome`, `endereco`, `data_base`) |
| GET | `/api/projetos`, `/api/projetos/{id}` | Lista / detalha com pavimentos e análises |
| POST | `/api/projetos/{id}/pavimentos` | Cria pavimento (`nome`, `repeticoes`) |
| GET | `/api/pavimentos/{id}` | Detalha pavimento |
| PUT | `/api/pavimentos/{id}/parametros` | Define parâmetros em metros e a unidade, se o DXF não declara |
| POST | `/api/pavimentos/{id}/arquivos` | Envia um DXF (nova revisão); processa em segundo plano e responde 202 |
| GET | `/api/analises/{id}` | Status, pendências por severidade e resultado completo |
| POST | `/api/analises/{id}/reprocessar` | Roda de novo com os parâmetros atuais |
| GET | `/api/analises/{id}/relatorio.xlsx` / `.md` | Baixa o relatório |

## Configuração (variáveis de ambiente)

| Variável | Padrão | Produção |
|---|---|---|
| `QUANTUM_DATABASE_URL` | `sqlite:///./dados/quantum.db` | `postgresql+psycopg://usuario:senha@host/quantum` |
| `QUANTUM_PASTA_ARQUIVOS` | `./dados/arquivos` | volume persistente |
| `QUANTUM_TAMANHO_MAX_MB` | `200` | |

## Decisões da etapa 1

- DWG é recusado com orientação para exportar DXF (sem conversor licenciado na nuvem).
- O arquivo é salvo com nome gerado por ids; o nome enviado fica só como metadado.
- Processamento em segundo plano no próprio processo (BackgroundTasks). Um DXF de 17 MB
  levou cerca de 6 s. Fila dedicada quando o volume pedir.
- Tabelas criadas automaticamente; migrações (Alembic) entram antes da primeira mudança de esquema em produção.
- Sem login por decisão do usuário (23/11/2026). Publicar com o endereço restrito à equipe até haver login.

## Interface web (etapa 2)

```bash
cd web && npm install && npm run dev      # http://127.0.0.1:5173, chama a API em :8000
npm run build                              # gera web/dist, servido pela API na raiz
```

Telas: empreendimentos → pavimentos e envio de DXF → análise (pendências, quantitativos por
disciplina, parâmetros com reprocessamento, camadas classificadas e sem disciplina, downloads).
