/// <reference lib="webworker" />
// Motor do Quantum no navegador: Pyodide (Python em WebAssembly) rodando o mesmo
// núcleo Python do repositório, dentro de um Web Worker para não travar a tela.

// Padrão: CDN oficial. Em testes sem internet: VITE_PYODIDE_URL=./pyodide/ (relativo ao site).
const PYODIDE_CFG: string = import.meta.env.VITE_PYODIDE_URL || "https://cdn.jsdelivr.net/pyodide/v0.27.2/full/";
// Pacotes que já vêm compilados na distribuição do Pyodide.
const PACOTES_PYODIDE = ["numpy", "pyyaml", "fonttools", "pyparsing", "typing-extensions", "shapely"];

type Pedido = { id: number; dxf: Blob; parametros: Record<string, number | string>; unidade: string | null; basePy: string; cortes?: { nome: string; dados: Blob }[] };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let pyodide: any = null;
let carregando: Promise<void> | null = null;

const avisar = (id: number, etapa: string) => postMessage({ id, tipo: "progresso", etapa });

async function iniciar(id: number, base: string) {
  if (pyodide) return;
  if (!carregando) {
    carregando = (async () => {
      avisar(id, "Carregando o Python no navegador (só na primeira vez)…");
      const PYODIDE_URL = new URL(PYODIDE_CFG, new URL("../", base)).href;
      const modulo = await import(/* @vite-ignore */ `${PYODIDE_URL}pyodide.mjs`);
      const py = await modulo.loadPyodide({ indexURL: PYODIDE_URL });
      avisar(id, "Instalando o núcleo Quantum…");
      await py.loadPackage(PACOTES_PYODIDE);
      const lista: string[] = await (await fetch(`${base}wheels.json`)).json();
      // Rodas puras (py3-none-any): basta descompactar no site-packages.
      // Evita o micropip, que falha com instalação de rodas locais sem dependências.
      const site: string = py.runPython("import site; site.getsitepackages()[0]");
      for (const nome of lista) {
        const r = await fetch(`${base}${nome}`);
        if (!r.ok) throw new Error(`Falha ao baixar ${nome} (${r.status})`);
        py.FS.writeFile(`/tmp/${nome}`, new Uint8Array(await r.arrayBuffer()));
        py.runPython(`import zipfile; zipfile.ZipFile("/tmp/${nome}").extractall("${site}")`);
        py.FS.unlink(`/tmp/${nome}`);
      }
      py.runPython("import importlib; importlib.invalidate_caches()");
      py.runPython("import quantum.navegador");
      pyodide = py;
    })();
  }
  try {
    await carregando;
  } catch (e) {
    carregando = null; // permite tentar de novo
    throw e;
  }
}

self.onmessage = async (ev: MessageEvent<Pedido>) => {
  const { id, dxf, parametros, unidade, basePy, cortes = [] } = ev.data;
  try {
    await iniciar(id, basePy);
    avisar(id, "Lendo o DXF e rodando os agentes…");
    // WORKERFS: o Python lê os arquivos direto dos Blobs, aos pedaços, sem copiá-los inteiros para a memória.
    const dir = `/entrada_${id}`;
    const blobs = [{ name: "planta.dxf", data: dxf }, ...cortes.map((c, i) => ({ name: `corte_${i}.dxf`, data: c.dados }))];
    pyodide.FS.mkdirTree(dir);
    pyodide.FS.mount(pyodide.FS.filesystems.WORKERFS, { blobs }, dir);
    const caminho = `${dir}/planta.dxf`;
    const caminhosCortes = cortes.map((_, i) => `${dir}/corte_${i}.dxf`);
    if (cortes.length) avisar(id, `Lendo o DXF, ${cortes.length} corte(s) e rodando os agentes…`);
    let texto: string;
    try {
      const modulo = pyodide.pyimport("quantum.navegador");
      texto = modulo.processar_dxf(caminho, JSON.stringify(parametros), unidade, JSON.stringify(caminhosCortes));
      modulo.destroy?.();
    } finally {
      pyodide.FS.unmount(dir);
      pyodide.FS.rmdir(dir);
    }
    postMessage({ id, tipo: "ok", saida: JSON.parse(texto) });
  } catch (e) {
    let msg = e instanceof Error ? e.message : String(e);
    if (/MemoryError|out of memory|Cannot enlarge memory|memory access out of bounds|Array buffer allocation failed/i.test(msg)) {
      pyodide = null;
      carregando = null;
      postMessage({
        id, tipo: "erro",
        erro: "Faltou memória no navegador para abrir este DXF. Feche outras abas e tente de novo; se repetir, exporte só o pavimento (sem outras pranchas, xrefs e hachuras desnecessárias) ou divida o arquivo.",
      });
      return;
    }
    if (/fatal error/i.test(msg)) {
      // O Pyodide não se recupera de um erro fatal: descarta e recarrega no próximo pedido.
      pyodide = null;
      carregando = null;
      postMessage({ id, tipo: "erro", erro: "O motor Python travou neste arquivo. Use Reprocessar; se repetir, envie o DXF para análise." });
      return;
    }
    // Erros do Python chegam com o traceback inteiro; mostra só a última linha.
    const linhas = msg.trim().split("\n");
    msg = linhas[linhas.length - 1] || msg;
    msg = msg.replace(/^quantum\.ingestao\.ErroIngestao:\s*/, "").replace(/^\w+Error:\s*/, "");
    postMessage({ id, tipo: "erro", erro: msg });
  }
};
