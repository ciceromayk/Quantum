// Camada de dados do Quantum, 100% no navegador (versão GitHub Pages).
// Mesma interface que a API do servidor usava; os dados ficam no IndexedDB e o
// processamento roda no Web Worker com Pyodide (motor.worker.ts).

import { banco } from "./banco";

export type Severidade = "bloqueante" | "alerta" | "info";
export type Status = "na_fila" | "processando" | "concluida" | "erro";

export interface AnaliseResumo {
  id: number;
  revisao: number;
  arquivo_nome: string;
  status: Status;
  erro: string | null;
  etapa?: string | null;
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

type ProjetoReg = Omit<Projeto, "pavimentos">;
type PavimentoReg = Omit<Pavimento, "analises">;
type AnaliseReg = Omit<AnaliseDetalhe, "resultado">;
interface RelatorioReg {
  resultado: Resultado;
  markdown: string;
  xlsx_base64: string;
}

export const AVISO =
  "Os quantitativos e valores gerados pelo Quantum são ESTIMATIVAS TÉCNICAS extraídas automaticamente do desenho. " +
  "Eles dependem da qualidade e da organização das camadas do arquivo e EXIGEM REVISÃO HUMANA por profissional " +
  "habilitado, com conferência em projeto e em obra, antes de qualquer uso para compra, contratação ou medição.";

const PARAMETROS_CONHECIDOS: Record<string, string> = {
  pe_direito: "Pé-direito (m)",
  altura_pilar: "Altura do lance de pilar (m)",
  espessura_laje: "Espessura da laje (m)",
};

const TAMANHO_MAX_MB = 200;
const agora = () => new Date().toISOString();

function exigir<T>(v: T | undefined, nome: string): T {
  if (v === undefined) throw new Error(`${nome} não encontrado`);
  return v;
}

// --- motor (Web Worker com Pyodide), uma análise por vez -----------------------------

let worker: Worker | null = null;
let fila: Promise<void> = Promise.resolve();
let seq = 0;

function motor(): Worker {
  if (!worker) worker = new Worker(new URL("./motor.worker.ts", import.meta.url), { type: "module" });
  return worker;
}

function rodarNoMotor(
  dxf: ArrayBuffer,
  parametros: Record<string, number>,
  unidade: string | null,
  aoProgredir: (etapa: string) => void,
): Promise<RelatorioReg> {
  const id = ++seq;
  const w = motor();
  return new Promise((ok, falha) => {
    const ouvir = (ev: MessageEvent) => {
      const m = ev.data;
      if (m.id !== id) return;
      if (m.tipo === "progresso") aoProgredir(m.etapa);
      else {
        w.removeEventListener("message", ouvir);
        if (m.tipo === "ok") ok(m.saida as RelatorioReg);
        else falha(new Error(m.erro));
      }
    };
    w.addEventListener("message", ouvir);
    const basePy = new URL("py/", document.baseURI).href;
    // copia o buffer: o original continua guardado no IndexedDB
    w.postMessage({ id, dxf: dxf.slice(0), parametros, unidade, basePy });
  });
}

async function atualizarAnalise(id: number, mudancas: Partial<AnaliseReg>) {
  const a = exigir(await banco.obter<AnaliseReg>("analises", id), "Análise");
  await banco.gravar("analises", { ...a, ...mudancas });
}

function enfileirar(analiseId: number) {
  fila = fila.then(() => processar(analiseId)).catch(() => undefined);
}

async function processar(analiseId: number) {
  const a = exigir(await banco.obter<AnaliseReg>("analises", analiseId), "Análise");
  const pav = exigir(await banco.obter<PavimentoReg>("pavimentos", a.pavimento_id), "Pavimento");
  const dxf = await banco.obter<ArrayBuffer>("arquivos", analiseId);
  if (!dxf) {
    await atualizarAnalise(analiseId, { status: "erro", erro: "Arquivo DXF não encontrado neste navegador. Envie de novo.", etapa: null });
    return;
  }
  await atualizarAnalise(analiseId, { status: "processando", erro: null, etapa: "Preparando…" });
  try {
    const saida = await rodarNoMotor(dxf, pav.parametros, pav.unidade, (etapa) => {
      atualizarAnalise(analiseId, { etapa });
    });
    await banco.gravar("relatorios", saida, analiseId);
    const sev: Partial<Record<Severidade, number>> = {};
    saida.resultado.pendencias.forEach((p) => (sev[p.severidade] = (sev[p.severidade] ?? 0) + 1));
    await atualizarAnalise(analiseId, {
      status: "concluida",
      etapa: null,
      concluido_em: agora(),
      pendencias_por_severidade: sev,
    });
  } catch (e) {
    await atualizarAnalise(analiseId, { status: "erro", erro: (e as Error).message, etapa: null, concluido_em: agora() });
  }
}

/** Ao abrir o app, nada está processando: análises presas de uma aba fechada viram erro. */
export async function recuperarInterrompidas() {
  for (const a of await banco.todos<AnaliseReg>("analises")) {
    if (a.status === "na_fila" || a.status === "processando") {
      await banco.gravar("analises", {
        ...a,
        status: "erro",
        etapa: null,
        erro: "Processamento interrompido (a página foi fechada). Use Reprocessar.",
      });
    }
  }
}

// --- leitura ---------------------------------------------------------------------------

async function montarPavimento(p: PavimentoReg, analises: AnaliseReg[]): Promise<Pavimento> {
  return {
    ...p,
    analises: analises
      .filter((a) => a.pavimento_id === p.id)
      .sort((x, y) => x.revisao - y.revisao)
      .map(({ pendencias_por_severidade: _s, pavimento_id: _p, ...r }) => r),
  };
}

async function montarProjeto(p: ProjetoReg): Promise<Projeto> {
  const pavs = (await banco.todos<PavimentoReg>("pavimentos")).filter((x) => x.projeto_id === p.id).sort((a, b) => a.id - b.id);
  const analises = await banco.todos<AnaliseReg>("analises");
  return { ...p, pavimentos: await Promise.all(pavs.map((x) => montarPavimento(x, analises))) };
}

function baixar(nome: string, conteudo: Blob) {
  const url = URL.createObjectURL(conteudo);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function nomeBase(a: AnaliseReg) {
  return `${a.arquivo_nome.replace(/\.[^.]+$/, "")}_R${a.revisao}`;
}

// --- API pública -------------------------------------------------------------------------

export const api = {
  saude: async () => ({ versao: "0.1.0", aviso: AVISO }),
  parametrosConhecidos: async () => PARAMETROS_CONHECIDOS,

  projetos: async (): Promise<Projeto[]> => {
    const lista = await banco.todos<ProjetoReg>("projetos");
    return Promise.all(lista.sort((a, b) => b.id - a.id).map(montarProjeto));
  },
  projeto: async (id: number) => montarProjeto(exigir(await banco.obter<ProjetoReg>("projetos", id), "Projeto")),

  criarProjeto: async (d: { nome: string; endereco?: string; data_base?: string }) => {
    if (!d.nome.trim()) throw new Error("Informe o nome");
    const reg = { nome: d.nome.trim(), endereco: d.endereco || null, data_base: d.data_base || null, criado_em: agora() };
    const id = await banco.gravar("projetos", reg);
    return { ...reg, id, pavimentos: [] } as Projeto;
  },

  criarPavimento: async (projetoId: number, d: { nome: string; repeticoes: number }) => {
    exigir(await banco.obter("projetos", projetoId), "Projeto");
    if (!d.nome.trim()) throw new Error("Informe o nome do pavimento");
    if (!Number.isInteger(d.repeticoes) || d.repeticoes < 1 || d.repeticoes > 200) throw new Error("Repetições entre 1 e 200");
    const reg = { projeto_id: projetoId, nome: d.nome.trim(), repeticoes: d.repeticoes, parametros: {}, unidade: null };
    const id = await banco.gravar("pavimentos", reg);
    return { ...reg, id, analises: [] } as Pavimento;
  },

  pavimento: async (id: number) => {
    const p = exigir(await banco.obter<PavimentoReg>("pavimentos", id), "Pavimento");
    return montarPavimento(p, await banco.todos<AnaliseReg>("analises"));
  },

  definirParametros: async (id: number, valores: Record<string, number>, unidade: string | null) => {
    const p = exigir(await banco.obter<PavimentoReg>("pavimentos", id), "Pavimento");
    for (const [k, v] of Object.entries(valores)) {
      if (!(v > 0 && v <= 100)) throw new Error(`${k} deve estar entre 0 e 100 metros`);
    }
    await banco.gravar("pavimentos", { ...p, parametros: valores, unidade });
    return api.pavimento(id);
  },

  enviarArquivo: async (pavimentoId: number, arquivo: File) => {
    exigir(await banco.obter("pavimentos", pavimentoId), "Pavimento");
    const ext = arquivo.name.toLowerCase().split(".").pop();
    if (ext === "dwg")
      throw new Error("DWG não é lido no navegador. Exporte o arquivo como DXF no CAD (Salvar como > DXF) e envie novamente.");
    if (ext !== "dxf") throw new Error("Envie um arquivo .dxf");
    if (arquivo.size > TAMANHO_MAX_MB * 1024 * 1024) throw new Error(`Arquivo maior que ${TAMANHO_MAX_MB} MB`);
    const anteriores = (await banco.todos<AnaliseReg>("analises")).filter((a) => a.pavimento_id === pavimentoId);
    const reg = {
      pavimento_id: pavimentoId,
      revisao: Math.max(0, ...anteriores.map((a) => a.revisao)) + 1,
      arquivo_nome: arquivo.name,
      status: "na_fila" as Status,
      erro: null,
      etapa: "Na fila",
      criado_em: agora(),
      concluido_em: null,
      pendencias_por_severidade: {},
    };
    const id = await banco.gravar("analises", reg);
    await banco.gravar("arquivos", await arquivo.arrayBuffer(), id);
    enfileirar(id);
    return { ...reg, id } as AnaliseResumo;
  },

  analise: async (id: number): Promise<AnaliseDetalhe> => {
    const a = exigir(await banco.obter<AnaliseReg>("analises", id), "Análise");
    const rel = await banco.obter<RelatorioReg>("relatorios", id);
    return { ...a, resultado: a.status === "concluida" && rel ? rel.resultado : null };
  },

  reprocessar: async (id: number) => {
    const a = exigir(await banco.obter<AnaliseReg>("analises", id), "Análise");
    if (a.status === "processando" || a.status === "na_fila") throw new Error("A análise ainda está em processamento");
    await atualizarAnalise(id, { status: "na_fila", etapa: "Na fila", erro: null });
    enfileirar(id);
    return api.analise(id);
  },

  baixarRelatorio: async (id: number, formato: "xlsx" | "md") => {
    const a = exigir(await banco.obter<AnaliseReg>("analises", id), "Análise");
    const rel = exigir(await banco.obter<RelatorioReg>("relatorios", id), "Relatório");
    if (formato === "md") {
      baixar(`${nomeBase(a)}.md`, new Blob([rel.markdown], { type: "text/markdown;charset=utf-8" }));
    } else {
      const bytes = Uint8Array.from(atob(rel.xlsx_base64), (c) => c.charCodeAt(0));
      baixar(`${nomeBase(a)}.xlsx`, new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
    }
  },

  /** Exporta o projeto (cadastro, parâmetros e resultados) em JSON. Os DXF não vão junto. */
  exportarProjeto: async (id: number) => {
    const p = exigir(await banco.obter<ProjetoReg>("projetos", id), "Projeto");
    const pavs = (await banco.todos<PavimentoReg>("pavimentos")).filter((x) => x.projeto_id === id);
    const analises = (await banco.todos<AnaliseReg>("analises")).filter((a) => pavs.some((x) => x.id === a.pavimento_id));
    const relatorios: Record<number, RelatorioReg | undefined> = {};
    for (const a of analises) relatorios[a.id] = await banco.obter<RelatorioReg>("relatorios", a.id);
    const dados = { formato: "quantum-projeto", versao: 1, exportado_em: agora(), aviso: AVISO, projeto: p, pavimentos: pavs, analises, relatorios };
    baixar(`${p.nome.replace(/[^\w\-À-ú ]+/g, "_")}.quantum.json`, new Blob([JSON.stringify(dados)], { type: "application/json" }));
  },

  importarProjeto: async (arquivo: File): Promise<number> => {
    let dados;
    try {
      dados = JSON.parse(await arquivo.text());
    } catch {
      throw new Error("Arquivo inválido: não é um projeto exportado pelo Quantum");
    }
    if (dados?.formato !== "quantum-projeto") throw new Error("Arquivo inválido: não é um projeto exportado pelo Quantum");
    const { id: _id, ...proj } = dados.projeto as ProjetoReg;
    const novoProjeto = await banco.gravar("projetos", proj);
    const mapaPav = new Map<number, number>();
    for (const pav of dados.pavimentos as PavimentoReg[]) {
      const { id, ...resto } = pav;
      mapaPav.set(id, await banco.gravar("pavimentos", { ...resto, projeto_id: novoProjeto }));
    }
    for (const a of dados.analises as AnaliseReg[]) {
      const { id, ...resto } = a;
      const novoPav = mapaPav.get(a.pavimento_id);
      if (novoPav === undefined) continue;
      const rel = dados.relatorios?.[id];
      const status: Status = a.status === "concluida" && rel ? "concluida" : "erro";
      const novo = await banco.gravar("analises", {
        ...resto,
        pavimento_id: novoPav,
        status,
        etapa: null,
        erro: status === "erro" ? "Importado sem resultado. Envie o DXF de novo para processar." : null,
      });
      if (rel) await banco.gravar("relatorios", rel, novo);
    }
    return novoProjeto;
  },
};
