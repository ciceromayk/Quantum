// Camada de dados do Quantum, 100% no navegador (versão GitHub Pages).
// Mesma interface que a API do servidor usava; os dados ficam no IndexedDB e o
// processamento roda no Web Worker com Pyodide (motor.worker.ts).

import { banco, type Loja } from "./banco";
import { prepararDesenho, type ConverterDwg } from "./conversao";

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
  /** Como o arquivo foi preparado (DWG convertido, .zip descompactado, DXF binário). */
  conversao?: string | null;
}

export interface Pavimento {
  id: number;
  projeto_id: number;
  nome: string;
  repeticoes: number;
  parametros: Parametros;
  unidade: string | null;
  analises: AnaliseResumo[];
  cortes: CorteResumo[];
}

/** Corte/vista em DXF usado para ler alturas de revestimento do pavimento. */
export interface CorteResumo {
  id: number;
  nome: string;
  tamanho: number;
  criado_em: string;
  conversao?: string | null;
}
interface CorteReg extends CorteResumo {
  pavimento_id: number;
  dados: Blob | ArrayBuffer; // Blob desde a v3 (fica no disco); ArrayBuffer em registros antigos
}

/** Valores em metros; "teto" = altura até o teto (usa o pé-direito). */
export type Parametros = Record<string, number | "teto">;

export interface AmbienteAcabamento {
  nome: string;
  area_rotulo: number;
  codigos: Partial<Record<"piso" | "parede" | "teto", string>>;
  area_contorno_m2: number | null;
  perimetro_m: number | null;
  contorno?: [number, number][] | null; // unidades do desenho
  contorno_origem?: string | null;
}

export interface Acabamentos {
  catalogo: Partial<Record<"piso" | "parede" | "teto" | "rodape", Record<string, string>>>;
  codigos_parede: string[];
  aviso_alturas: string;
  ambientes: AmbienteAcabamento[];
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
  parametros: Parametros;
  acabamentos?: Acabamentos | Record<string, never>;
  aviso: string;
}

export interface AnaliseDetalhe extends AnaliseResumo {
  pavimento_id: number;
  pendencias_por_severidade: Partial<Record<Severidade, number>>;
  resultado: Resultado | null;
}

type ProjetoReg = Omit<Projeto, "pavimentos">;
type PavimentoReg = Omit<Pavimento, "analises" | "cortes">;
type AnaliseReg = Omit<AnaliseDetalhe, "resultado">;
interface RelatorioReg {
  resultado: Resultado;
  markdown: string;
  xlsx_base64: string;
  dxf_acabamentos_base64?: string | null;
  geometria?: Geometria | { erro: string } | null;
}

/** Desenho do Model simplificado para o visualizador (metros). */
export interface Geometria {
  caixa: [number, number, number, number] | null;
  foco?: [number, number, number, number] | null; // miolo do desenho, para enquadrar
  camadas: Record<string, { cor: string; linhas: number[][] }>;
  textos: [number, number, number, string, string][]; // x, y, altura, texto, camada
  pontos: number;
  cortado: boolean;
  fator_m: number;
  geradas?: string[]; // camadas das polilinhas de acabamento geradas (QTD-*)
  largura_gerada?: number; // espessura delas, em metros
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

/** Formatos aceitos no envio (planta e cortes). */
export const ACEITOS = ".dxf,.dwg,.zip";

/** DWG vira DXF num worker próprio, encerrado no fim para liberar a memória do WebAssembly. */
const converterDwg: ConverterDwg = (dwg, versao) =>
  new Promise((ok, falha) => {
    const w = new Worker(new URL("./conversor.worker.ts", import.meta.url), { type: "module" });
    const fim = () => w.terminate();
    w.onmessage = (ev) => {
      fim();
      if (ev.data.tipo === "ok") ok({ dxf: ev.data.dxf as Blob, aviso: ev.data.aviso });
      else falha(new Error(ev.data.erro));
    };
    w.onmessageerror = () => {
      fim();
      falha(new Error(`A conversão do DWG não devolveu o resultado (provável falta de memória). Exporte o desenho como DXF e envie o DXF.`));
    };
    w.onerror = (ev) => {
      fim();
      falha(new Error(`O leitor de DWG não carregou (${ev.message || "erro no worker"}). Exporte o desenho como DXF e envie o DXF.`));
    };
    w.postMessage({ dwg, versao });
  });
/** DWG acima disso pode esgotar a memória do navegador na conversão (a aba pode até fechar). */
export const DWG_GRANDE_MB = 40;

// --- conversão interrompida ---------------------------------------------------------------
// Se a aba cair no meio da conversão (falta de memória), nenhum erro chega à tela. Uma marca
// no localStorage, apagada no fim, permite explicar o que houve quando a página reabre.

const MARCA = "quantum:preparo-em-andamento";

export interface PreparoInterrompido {
  tipo: "planta" | "corte";
  nome: string;
  tamanho: number;
  pavimento_id: number;
}

function marcar(m: PreparoInterrompido | null) {
  try {
    if (m) localStorage.setItem(MARCA, JSON.stringify(m));
    else localStorage.removeItem(MARCA);
  } catch {
    /* navegador sem localStorage: segue sem a marca */
  }
}

async function preparar(tipo: PreparoInterrompido["tipo"], pavimentoId: number, arquivo: File, aoProgredir?: (etapa: string) => void) {
  marcar({ tipo, nome: arquivo.name, tamanho: arquivo.size, pavimento_id: pavimentoId });
  try {
    return await prepararDesenho(arquivo, arquivo.name, converterDwg, aoProgredir);
  } finally {
    marcar(null);
  }
}

/** Lê e apaga a marca de um preparo que não terminou (a aba fechou ou travou no meio). */
export function preparoInterrompido(): PreparoInterrompido | null {
  try {
    const v = localStorage.getItem(MARCA);
    localStorage.removeItem(MARCA);
    return v ? (JSON.parse(v) as PreparoInterrompido) : null;
  } catch {
    return null;
  }
}

/** Acima disso a planta pode faltar memória no navegador (o corte é lido em fluxo e aguenta mais). */
export const PLANTA_GRANDE_MB = 150;

const comoBlob = (d: Blob | ArrayBuffer) => (d instanceof Blob ? d : new Blob([d]));
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
  dxf: Blob,
  parametros: Parametros,
  unidade: string | null,
  cortes: { nome: string; dados: Blob }[],
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
    // Blobs vão por referência: o worker lê direto do disco, sem copiar o arquivo inteiro na memória.
    w.postMessage({ id, dxf, parametros, unidade, basePy, cortes });
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
  const guardado = await banco.obter<Blob | ArrayBuffer>("arquivos", analiseId);
  const dxf = guardado && comoBlob(guardado);
  if (!dxf) {
    await atualizarAnalise(analiseId, { status: "erro", erro: "Arquivo DXF não encontrado neste navegador. Envie de novo.", etapa: null });
    return;
  }
  await atualizarAnalise(analiseId, { status: "processando", erro: null, etapa: "Preparando…" });
  try {
    const cortes = (await banco.todos<CorteReg>("cortes"))
      .filter((c) => c.pavimento_id === pav.id)
      .map((c) => ({ nome: c.nome, dados: comoBlob(c.dados) }));
    const saida = await rodarNoMotor(dxf, pav.parametros, pav.unidade, cortes, (etapa) => {
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
  const cortes = (await banco.todos<CorteReg>("cortes"))
    .filter((c) => c.pavimento_id === p.id)
    .map(({ id, nome, tamanho, criado_em, conversao }) => ({ id, nome, tamanho, criado_em, conversao }));
  return {
    ...p,
    cortes,
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

// --- exclusão ------------------------------------------------------------------------------

const ocupada = (a: AnaliseReg) => a.status === "na_fila" || a.status === "processando";

const chavesDaAnalise = (id: number): [Loja, number][] => [
  ["arquivos", id],
  ["relatorios", id],
  ["analises", id],
];

/** Tudo o que pertence aos pavimentos (revisões e cortes). Recusa se algo ainda processa. */
async function chavesDosPavimentos(ids: number[]): Promise<[Loja, number][]> {
  const pavs = new Set(ids);
  const analises = (await banco.todos<AnaliseReg>("analises")).filter((a) => pavs.has(a.pavimento_id));
  const presa = analises.find(ocupada);
  if (presa) throw new Error(`R${presa.revisao} (${presa.arquivo_nome}) ainda está em processamento. Aguarde terminar para excluir.`);
  const cortes = (await banco.todos<CorteReg>("cortes")).filter((c) => pavs.has(c.pavimento_id));
  return [...analises.flatMap((a) => chavesDaAnalise(a.id)), ...cortes.map((c) => ["cortes", c.id] as [Loja, number])];
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
    return { ...reg, id, analises: [], cortes: [] } as Pavimento;
  },

  pavimento: async (id: number) => {
    const p = exigir(await banco.obter<PavimentoReg>("pavimentos", id), "Pavimento");
    return montarPavimento(p, await banco.todos<AnaliseReg>("analises"));
  },

  definirParametros: async (id: number, valores: Parametros, unidade: string | null) => {
    const p = exigir(await banco.obter<PavimentoReg>("pavimentos", id), "Pavimento");
    for (const [k, v] of Object.entries(valores)) {
      if (v === "teto" && k.startsWith("altura_parede_")) continue;
      if (!(typeof v === "number" && v > 0 && v <= 100)) throw new Error(`${k} deve estar entre 0 e 100 metros`);
    }
    await banco.gravar("pavimentos", { ...p, parametros: valores, unidade });
    return api.pavimento(id);
  },

  enviarArquivo: async (pavimentoId: number, arquivo: File, aoProgredir?: (etapa: string) => void) => {
    exigir(await banco.obter("pavimentos", pavimentoId), "Pavimento");
    const { dxf, nota } = await preparar("planta", pavimentoId, arquivo, aoProgredir);
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
      conversao: nota,
    };
    const id = await banco.gravar("analises", reg);
    await banco.gravar("arquivos", dxf, id); // o DXF (Blob) fica no disco do navegador; DWG e .zip já convertidos
    enfileirar(id);
    return { ...reg, id } as AnaliseResumo;
  },

  temDxfAcabamentos: async (id: number) => !!(await banco.obter<RelatorioReg>("relatorios", id))?.dxf_acabamentos_base64,

  /** Cortes valem para as próximas análises do pavimento (use Reprocessar nas anteriores). */
  enviarCorte: async (pavimentoId: number, arquivo: File, aoProgredir?: (etapa: string) => void) => {
    exigir(await banco.obter("pavimentos", pavimentoId), "Pavimento");
    const { dxf, nota } = await preparar("corte", pavimentoId, arquivo, aoProgredir);
    const reg = { pavimento_id: pavimentoId, nome: arquivo.name, tamanho: dxf.size, criado_em: agora(), dados: dxf, conversao: nota };
    try {
      await banco.gravar("cortes", reg);
    } catch (e) {
      throw new Error(`Não foi possível guardar o corte no navegador (${(e as Error).message || e}). Libere espaço em disco ou remova análises antigas.`);
    }
  },
  removerCorte: async (id: number) => banco.apagar("cortes", id),

  /** Apaga uma revisão da planta: o DXF guardado, a análise e os relatórios gerados. */
  excluirAnalise: async (id: number) => {
    const a = exigir(await banco.obter<AnaliseReg>("analises", id), "Análise");
    if (ocupada(a)) throw new Error(`R${a.revisao} ainda está em processamento. Aguarde terminar para excluir.`);
    await banco.apagarVarios(chavesDaAnalise(id));
  },

  /** Apaga o pavimento com todas as revisões, análises e cortes. */
  excluirPavimento: async (id: number) => {
    exigir(await banco.obter<PavimentoReg>("pavimentos", id), "Pavimento");
    await banco.apagarVarios([...(await chavesDosPavimentos([id])), ["pavimentos", id]]);
  },

  /** Apaga o empreendimento inteiro: pavimentos, arquivos, cortes, análises e relatórios. */
  excluirProjeto: async (id: number) => {
    exigir(await banco.obter<ProjetoReg>("projetos", id), "Projeto");
    const pavs = (await banco.todos<PavimentoReg>("pavimentos")).filter((p) => p.projeto_id === id).map((p) => p.id);
    await banco.apagarVarios([...(await chavesDosPavimentos(pavs)), ...pavs.map((p) => ["pavimentos", p] as [Loja, number]), ["projetos", id]]);
  },

  /** Espaço que o Quantum ocupa neste navegador (null se o navegador não informa). */
  espacoUsado: async (): Promise<{ usado: number; total: number } | null> => {
    try {
      const e = await navigator.storage?.estimate?.();
      return e && e.usage !== undefined ? { usado: e.usage, total: e.quota ?? 0 } : null;
    } catch {
      return null;
    }
  },

  /** Geometria para o visualizador; null se a análise é de antes do visualizador (use Reprocessar). */
  geometria: async (id: number): Promise<Geometria | null> => {
    const g = (await banco.obter<RelatorioReg>("relatorios", id))?.geometria;
    if (!g) return null;
    if ("erro" in g) throw new Error(`Não foi possível montar o desenho: ${g.erro}`);
    return g;
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

  baixarRelatorio: async (id: number, formato: "xlsx" | "md" | "dxf") => {
    const a = exigir(await banco.obter<AnaliseReg>("analises", id), "Análise");
    const rel = exigir(await banco.obter<RelatorioReg>("relatorios", id), "Relatório");
    if (formato === "dxf") {
      if (!rel.dxf_acabamentos_base64) throw new Error("Nenhum ambiente com contorno: o DXF de acabamentos não foi gerado.");
      const bytes = Uint8Array.from(atob(rel.dxf_acabamentos_base64), (c) => c.charCodeAt(0));
      baixar(`${nomeBase(a)}_acabamentos.dxf`, new Blob([bytes], { type: "application/dxf" }));
    } else if (formato === "md") {
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
    for (const a of analises) {
      const r = await banco.obter<RelatorioReg>("relatorios", a.id);
      // o DXF gerado é grande e sai de novo ao reprocessar: não vai no backup
      relatorios[a.id] = r && { ...r, dxf_acabamentos_base64: null, geometria: null };
    }
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
