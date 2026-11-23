// Cliente da API do Quantum. Todas as rotas ficam sob /api.

export type Severidade = "bloqueante" | "alerta" | "info";

export interface AnaliseResumo {
  id: number;
  revisao: number;
  arquivo_nome: string;
  status: "na_fila" | "processando" | "concluida" | "erro";
  erro: string | null;
  criado_em: string;
  concluido_em: string | null;
}

export interface Pavimento {
  id: number;
  projeto_id: number;
  nome: string;
  repeticoes: number;
  parametros: Record<string, number>;
  unidade: string | null;
  analises: AnaliseResumo[];
}

export interface Projeto {
  id: number;
  nome: string;
  endereco: string | null;
  data_base: string | null;
  criado_em: string;
  pavimentos: Pavimento[];
}

export interface Item {
  disciplina: string;
  codigo: string;
  descricao: string;
  unidade: string;
  quantidade: number | null;
  camadas: string[];
  detalhe: string | null;
  handles: string[];
  observacao: string | null;
}

export interface Pendencia {
  disciplina: string;
  severidade: Severidade;
  mensagem: string;
  camada: string | null;
  handles: string[];
  acao_sugerida: string | null;
}

export interface Resultado {
  desenho: { arquivo: string; versao_dxf: string; unidade: string | null; origem_unidade: string; total_entidades: number };
  itens: Item[];
  pendencias: Pendencia[];
  camadas_nao_classificadas: Record<string, number>;
  parametros: Record<string, number>;
  aviso: string;
}

export interface AnaliseDetalhe extends AnaliseResumo {
  pavimento_id: number;
  pendencias_por_severidade: Partial<Record<Severidade, number>>;
  resultado: Resultado | null;
}

async function req<T>(caminho: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${caminho}`, init);
  if (!r.ok) {
    let msg = `Erro ${r.status}`;
    try {
      const corpo = await r.json();
      if (typeof corpo.detail === "string") msg = corpo.detail;
      else if (Array.isArray(corpo.detail)) msg = corpo.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* corpo não é JSON */
    }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  saude: () => req<{ versao: string; aviso: string }>("/saude"),
  parametrosConhecidos: () => req<Record<string, string>>("/parametros-conhecidos"),
  projetos: () => req<Projeto[]>("/projetos"),
  projeto: (id: number) => req<Projeto>(`/projetos/${id}`),
  criarProjeto: (d: { nome: string; endereco?: string; data_base?: string }) => req<Projeto>("/projetos", json("POST", d)),
  criarPavimento: (projetoId: number, d: { nome: string; repeticoes: number }) =>
    req<Pavimento>(`/projetos/${projetoId}/pavimentos`, json("POST", d)),
  pavimento: (id: number) => req<Pavimento>(`/pavimentos/${id}`),
  definirParametros: (id: number, valores: Record<string, number>, unidade: string | null) =>
    req<Pavimento>(`/pavimentos/${id}/parametros`, json("PUT", { valores, unidade })),
  enviarArquivo: (pavimentoId: number, arquivo: File) => {
    const fd = new FormData();
    fd.append("arquivo", arquivo);
    return req<AnaliseResumo>(`/pavimentos/${pavimentoId}/arquivos`, { method: "POST", body: fd });
  },
  analise: (id: number) => req<AnaliseDetalhe>(`/analises/${id}`),
  reprocessar: (id: number) => req<AnaliseResumo>(`/analises/${id}/reprocessar`, { method: "POST" }),
  urlRelatorio: (id: number, formato: "xlsx" | "md") => `/api/analises/${id}/relatorio.${formato}`,
};
