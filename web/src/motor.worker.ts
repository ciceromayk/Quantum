/// <reference lib="webworker" />
// Motor do Quantum no navegador: Pyodide (Python em WebAssembly) rodando o mesmo
// núcleo Python do repositório, dentro de um Web Worker para não travar a tela.

// Padrão: CDN oficial. Em testes sem internet: VITE_PYODIDE_URL=./pyodide/ (relativo ao site).
const PYODIDE_CFG: string = import.meta.env.VITE_PYODIDE_URL || "https://cdn.jsdelivr.net/pyodide/v0.27.2/full/";
// Pacotes que já vêm compilados na distribuição do Pyodide.
const PACOTES_PYODIDE = ["numpy", "pyyaml", "fonttools", "pyparsing", "typing-extensions", "shapely"];

type Pedido = { id: number; dxf: ArrayBuffer; parametros: Record<string, number | string>; unidade: string | null; basePy: string; cortes?: { nome: string; dados: ArrayBuffer }[] };

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
    const caminho = `/tmp/entrada_${id}.dxf`;
    pyodide.FS.writeFile(caminho, new Uint8Array(dxf));
    const caminhosCortes = cortes.map((c, i) => {
      const p = `/tmp/corte_${id}_${i}.dxf`;
      pyodide.FS.writeFile(p, new Uint8Array(c.dados));
      return p;
    });
    if (cortes.length) avisar(id, `Lendo o DXF, ${cortes.length} corte(s) e rodando os agentes…`);
    const modulo = pyodide.pyimport("quantum.navegador");
    const texto: string = modulo.processar_dxf(caminho, JSON.stringify(parametros), unidade, JSON.stringify(caminhosCortes));
    modulo.destroy?.();
    pyodide.FS.unlink(caminho);
    caminhosCortes.forEach((p) => pyodide.FS.unlink(p));
    postMessage({ id, tipo: "ok", saida: JSON.parse(texto) });
  } catch (e) {
    let msg = e instanceof Error ? e.message : String(e);
    // Erros do Python chegam com o traceback inteiro; mostra só a última linha.
    const linhas = msg.trim().split("\n");
    msg = linhas[linhas.length - 1] || msg;
    msg = msg.replace(/^quantum\.ingestao\.ErroIngestao:\s*/, "").replace(/^\w+Error:\s*/, "");
    postMessage({ id, tipo: "erro", erro: msg });
  }
};
