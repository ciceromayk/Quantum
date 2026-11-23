# API do Quantum (etapa 1)

Servidor: `uvicorn quantum_api.main:app --reload` → documentação interativa em `/docs`.

| Método | Rota | O que faz |
|---|---|---|
| GET | `/saude` | Versão e aviso de estimativa |
| GET | `/parametros-conhecidos` | Parâmetros usados pelas regras padrão |
| POST | `/projetos` | Cria empreendimento (`nome`, `endereco`, `data_base`) |
| GET | `/projetos`, `/projetos/{id}` | Lista / detalha com pavimentos e análises |
| POST | `/projetos/{id}/pavimentos` | Cria pavimento (`nome`, `repeticoes`) |
| GET | `/pavimentos/{id}` | Detalha pavimento |
| PUT | `/pavimentos/{id}/parametros` | Define parâmetros em metros e a unidade, se o DXF não declara |
| POST | `/pavimentos/{id}/arquivos` | Envia um DXF (nova revisão); processa em segundo plano e responde 202 |
| GET | `/analises/{id}` | Status, pendências por severidade e resultado completo |
| POST | `/analises/{id}/reprocessar` | Roda de novo com os parâmetros atuais |
| GET | `/analises/{id}/relatorio.xlsx` / `.md` | Baixa o relatório |

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
- Ainda sem login: entra na etapa 2, antes de publicar na internet.
